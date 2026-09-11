"""Regression coverage for the public signature export and provenance UX."""

from __future__ import annotations

import base64
import importlib
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from click.testing import CliRunner
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from stamp_cli.core import raster
from stamp_cli.styles.esign import signature as signature_mod


cli = importlib.import_module("stamp_cli.cli").cli
STYLE = signature_mod.STYLE
SVG_NS = "{http://www.w3.org/2000/svg}"
EMBEDDED_PNG = re.compile(r"data:image/png;base64,([A-Za-z0-9+/=]+)")


def _invoke_sign(tmp_path: Path, *extra: str, stem: str = "signature"):
    result = CliRunner().invoke(
        cli,
        ["sign", "--name", "Alex Morgan", "-o", str(tmp_path / stem), "--json", *extra],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def _svg_root(path: Path) -> ET.Element:
    return ET.fromstring(path.read_bytes())


def _svg_text(root: ET.Element) -> list[str]:
    return [node.text or "" for node in root.findall(f".//{SVG_NS}text")]


def _embedded_png(svg: str) -> bytes:
    match = EMBEDDED_PNG.search(svg)
    assert match, "expected the processed signature PNG to be embedded"
    return base64.b64decode(match.group(1))


def _inspect(path: Path) -> dict:
    result = CliRunner().invoke(cli, ["inspect", str(path), "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def _render_alpha_bbox(result) -> tuple[int, int, int, int]:
    blob = raster.render_png(
        result.svg,
        font_files=[font.file_path for font in result.fonts_used],
        width=420,
        background="transparent",
        skip_system_fonts=True,
    )
    with Image.open(io.BytesIO(blob)) as image:
        bbox = image.convert("RGBA").getchannel("A").getbbox()
    assert bbox is not None
    return bbox


def _synthetic_signature(path: Path, size=(120, 48)) -> Path:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.line([(0, size[1] - 1), (size[0] // 3, 0), (size[0] - 1, size[1] - 1)],
              fill="black", width=3)
    image.save(path)
    return path


def test_sign_defaults_to_classic_frame_and_visible_reference(tmp_path):
    envelope = _invoke_sign(tmp_path, "--format", "svg")
    root = _svg_root(Path(envelope["paths"]["svg"]))
    reference = envelope["reference"]

    assert envelope["normalized_params"]["layout"] == "classic"
    assert envelope["normalized_params"]["bracket"] == "round"
    assert envelope["normalized_params"]["show_id"] is True
    assert root.find(f"{SVG_NS}path") is not None
    assert "Signed by:" in _svg_text(root)
    assert reference in _svg_text(root)


@pytest.mark.parametrize(
    ("layout", "expected_height", "text_count"),
    [("clean", "200", 4), ("signature-only", "140", 1)],
)
def test_sign_layout_toggles_clean_and_bare(tmp_path, layout, expected_height, text_count):
    envelope = _invoke_sign(tmp_path, "--format", "svg", "--layout", layout, stem=layout)
    root = _svg_root(Path(envelope["paths"]["svg"]))
    texts = _svg_text(root)

    assert envelope["normalized_params"]["layout"] == layout
    assert envelope["normalized_params"]["bracket"] == "none"
    assert root.attrib["viewBox"].split()[-1] == expected_height
    assert len(texts) == text_count
    if layout == "clean":
        assert envelope["normalized_params"]["show_name"] is True
        assert "Alex Morgan" in texts
        assert envelope["reference"] in texts
    else:
        assert envelope["normalized_params"]["show_id"] is False
        assert envelope["normalized_params"]["show_name"] is False
        assert texts == ["Alex Morgan"]


def test_hidden_id_remains_inspectable_in_svg_and_png(tmp_path):
    envelope = _invoke_sign(tmp_path, "--no-show-id", "--format", "both")
    reference = envelope["reference"]
    svg_path = Path(envelope["paths"]["svg"])
    png_path = Path(envelope["paths"]["png"])

    assert envelope["normalized_params"]["show_id"] is False
    assert reference not in _svg_text(_svg_root(svg_path))
    assert _inspect(svg_path)["reference"] == reference
    assert _inspect(png_path)["reference"] == reference

    # The lower content zone is empty when the visible fingerprint is disabled.
    with Image.open(png_path) as image:
        rgba = image.convert("RGBA")
        scale = rgba.width / 420
        id_zone = rgba.crop((int(125 * scale), int(158 * scale),
                             int(400 * scale), int(184 * scale)))
        assert id_zone.getchannel("A").getextrema()[1] == 0


def test_inspect_checksums_equal_export_envelope(tmp_path):
    envelope = _invoke_sign(tmp_path, "--format", "both")
    for kind in ("svg", "png"):
        report = _inspect(Path(envelope["paths"][kind]))
        assert report["sha256"] == envelope["checksums"][kind]


def test_verify_matches_original_and_rejects_modified_valid_artifacts(tmp_path):
    envelope = _invoke_sign(tmp_path, "--format", "both")

    for kind in ("svg", "png"):
        path = Path(envelope["paths"][kind])
        expected = envelope["checksums"][kind]
        original = CliRunner().invoke(
            cli, ["verify", str(path), "--sha256", expected, "--json"]
        )
        assert original.exit_code == 0, original.output
        assert json.loads(original.stdout)["matches"] is True

        if kind == "svg":
            path.write_text(path.read_text(encoding="utf-8").replace("</svg>", "\n</svg>"),
                            encoding="utf-8")
        else:
            with Image.open(path) as source:
                metadata = source.info["stamp-cli"]
                changed = source.convert("RGBA")
            changed.putpixel((0, 0), (255, 0, 0, 255))
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text("stamp-cli", metadata)
            changed.save(path, pnginfo=pnginfo)

        modified = CliRunner().invoke(
            cli, ["verify", str(path), "--sha256", expected, "--json"]
        )
        assert modified.exit_code == 1
        report = json.loads(modified.stdout)
        assert report["ok"] is False
        assert report["matches"] is False


@pytest.mark.parametrize("checksum", ["abc", "g" * 64, "0" * 63])
def test_verify_rejects_malformed_checksums_as_user_errors(tmp_path, checksum):
    envelope = _invoke_sign(tmp_path, "--format", "svg")
    result = CliRunner().invoke(
        cli,
        ["verify", envelope["paths"]["svg"], "--sha256", checksum, "--json"],
    )

    assert result.exit_code == 1
    error = json.loads(result.stdout)
    assert error["ok"] is False
    assert error["exit_code"] == 1
    assert "64 hexadecimal" in error["error"]


def test_export_metadata_is_minimal_and_drops_source_path_and_exif(tmp_path):
    source_path = tmp_path / "synthetic-source-with-private-marker.jpg"
    image = Image.new("RGB", (160, 60), "white")
    ImageDraw.Draw(image).line([(5, 52), (70, 5), (155, 50)], fill="black", width=5)
    exif = Image.Exif()
    exif[315] = "SYNTHETIC_PRIVATE_AUTHOR_MARKER"
    exif[270] = "SYNTHETIC_PRIVATE_EXIF_MARKER"
    image.save(source_path, exif=exif)

    envelope = _invoke_sign(
        tmp_path, "--signature", str(source_path), "--format", "both", stem="metadata"
    )
    expected_keys = {"schema", "style", "reference"}

    svg_path = Path(envelope["paths"]["svg"])
    metadata_node = _svg_root(svg_path).find(f"{SVG_NS}metadata[@id='stamp-cli']")
    assert metadata_node is not None
    svg_metadata = json.loads(metadata_node.text or "{}")
    assert set(svg_metadata) == expected_keys

    png_path = Path(envelope["paths"]["png"])
    with Image.open(png_path) as rendered:
        png_metadata = json.loads(rendered.info["stamp-cli"])
        assert "exif" not in rendered.info
    assert set(png_metadata) == expected_keys

    forbidden = (
        str(source_path).encode(), source_path.name.encode(),
        b"SYNTHETIC_PRIVATE_AUTHOR_MARKER", b"SYNTHETIC_PRIVATE_EXIF_MARKER",
    )
    for artifact in (svg_path.read_bytes(), png_path.read_bytes()):
        assert all(marker not in artifact for marker in forbidden)


def test_white_padding_does_not_change_reference_or_cropped_pixels(tmp_path):
    tight = _synthetic_signature(tmp_path / "tight.png", size=(64, 24))
    padded = tmp_path / "padded.png"
    with Image.open(tight) as mark:
        canvas = Image.new("RGB", (180, 90), "white")
        canvas.paste(mark, (51, 33))
        canvas.save(padded)

    tight_result = STYLE.build_svg(signature=str(tight), name="Synthetic Signer")
    padded_result = STYLE.build_svg(signature=str(padded), name="Synthetic Signer")

    assert tight_result.normalized_params["sig_id"] == padded_result.normalized_params["sig_id"]
    assert _embedded_png(tight_result.svg) == _embedded_png(padded_result.svg)


def test_oversized_white_padding_does_not_resize_identical_small_ink(tmp_path):
    tight = _synthetic_signature(tmp_path / "tight-small-ink.png", size=(64, 24))
    padded = tmp_path / "oversized-white-padding.png"
    with Image.open(tight) as mark:
        canvas = Image.new("RGB", (2048, 1200), "white")
        canvas.paste(mark, (993, 588))
        canvas.save(padded)

    tight_result = STYLE.build_svg(signature=str(tight), name="Synthetic Signer")
    padded_result = STYLE.build_svg(signature=str(padded), name="Synthetic Signer")

    assert tight_result.normalized_params["max_px"] == 1600
    assert padded_result.normalized_params["max_px"] == 1600
    assert tight_result.normalized_params["image_px"] == [64, 24]
    assert padded_result.normalized_params["image_px"] == [64, 24]
    assert _embedded_png(tight_result.svg) == _embedded_png(padded_result.svg)
    assert tight_result.normalized_params["sig_id"] == padded_result.normalized_params["sig_id"]


def test_tall_classic_signature_grows_frame_and_caps_ink_height(tmp_path):
    path = tmp_path / "tall.png"
    image = Image.new("RGB", (40, 120), "white")
    ImageDraw.Draw(image).line([(20, 0), (20, 119)], fill="black", width=4)
    image.save(path)

    result = STYLE.build_svg(signature=str(path), name="Tall Synthetic")
    root = ET.fromstring(result.svg)
    embedded = root.find(f"{SVG_NS}image")
    assert embedded is not None

    assert float(root.attrib["viewBox"].split()[-1]) > 200
    assert float(embedded.attrib["width"]) == 368
    assert float(embedded.attrib["height"]) == 240
    assert result.normalized_params["image_px"][1] > result.normalized_params["image_px"][0]


def test_typed_name_length_limit_and_legible_long_name_behavior():
    with pytest.raises(ValueError, match="at most 160 characters"):
        STYLE.build_svg(signature="typed", name="A" * 161)

    try:
        result = STYLE.build_svg(signature="typed", name="W" * 160, layout="signature-only")
    except ValueError as error:
        assert "too long to fit legibly" in str(error).lower()
    else:
        left, top, right, bottom = _render_alpha_bbox(result)
        assert left >= 17 and top >= 11
        assert right <= 403 and bottom <= 129


def test_typed_signature_rejects_blank_name_with_legible_cli_error(tmp_path):
    result = CliRunner().invoke(
        cli,
        ["sign", "--name", "   ", "-o", str(tmp_path / "blank.svg"), "--json"],
    )
    assert result.exit_code == 1
    error = json.loads(result.stdout)
    assert error["exit_code"] == 1
    assert "non-empty --name" in error["error"]


def test_signature_rejects_multiframe_source(tmp_path):
    path = tmp_path / "animated.gif"
    frames = [Image.new("RGB", (16, 16), color) for color in ("black", "white")]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=10, loop=0)

    with pytest.raises(ValueError, match="single-frame"):
        STYLE.build_svg(signature=str(path), name="Synthetic Signer")


def test_signature_rejects_over_25_megapixels_before_decode(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-large.png"
    path.write_bytes(b"synthetic placeholder")

    class SyntheticOversizeImage:
        width = 5001
        height = 5001

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def load(self):
            raise AssertionError("oversized image must be rejected before decoding")

    monkeypatch.setattr(signature_mod.Image, "open", lambda unused: SyntheticOversizeImage())
    with pytest.raises(ValueError, match="25 megapixels"):
        STYLE.build_svg(signature=str(path), name="Synthetic Signer")


def test_sign_rejects_invalid_xml_characters(tmp_path):
    result = CliRunner().invoke(
        cli,
        ["sign", "--name", "Alex\x01Morgan", "-o", str(tmp_path / "invalid.svg"), "--json"],
    )
    assert result.exit_code == 1
    error = json.loads(result.stdout)
    assert error["exit_code"] == 1
    assert "invalid xml characters" in error["error"].lower()


@pytest.mark.parametrize("name", [
    "Alex Morgan",
    "Alexandra Morgan-Wellington Jordan Lee Fairchild I",
    "W" * 160,
])
def test_typed_names_fit_or_report_font_specific_legibility_limit(name):
    # Script faces differ across platforms. Names that fit at the minimum
    # must render; wider names must be refused instead of clipped or condensed.
    profile = signature_mod.default_resolver.resolve("script")
    face = ImageFont.truetype(profile.file_path, 18 * 4, index=profile.face_index)
    left, top, right, bottom = face.getbbox(name, anchor="ls")
    if right - left > 384 * 4 or bottom - top > 116 * 4:
        with pytest.raises(ValueError, match="too long to fit legibly"):
            STYLE.build_svg(signature="typed", name=name, layout="signature-only")
        return
    result = STYLE.build_svg(signature="typed", name=name, layout="signature-only")

    left, top, right, bottom = _render_alpha_bbox(result)
    assert left >= 17 and top >= 11
    assert right <= 403 and bottom <= 129

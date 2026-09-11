"""Focused tests for the ``esign.signature`` DocuSign-style overlay.

The registry suite (test_styles.py) already covers protocol/build/raster/
determinism over the DEFAULT params. These exercise the parts unique to this
style: the image pipeline, the white-knockout, the deterministic content-hash
ID, PII-safety of the default, and the bracket variants.
"""

from __future__ import annotations

import base64
import io
import re

import pytest
from PIL import Image, ImageDraw

from stamp_cli import styles
from stamp_cli.core import raster
from stamp_cli.styles.esign import signature as sig_mod

STYLE = sig_mod.STYLE
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

_B64_RE = re.compile(r"data:image/png;base64,([A-Za-z0-9+/=]+)")
_ID_RE = re.compile(r">([0-9A-F]{32})</text>")


def _embedded_png(svg: str) -> bytes:
    m = _B64_RE.search(svg)
    assert m, "expected an embedded base64 PNG in the SVG"
    return base64.b64decode(m.group(1))


def _id_text(svg: str) -> str:
    m = _ID_RE.search(svg)
    assert m, "expected a 32-hex ID text node in the SVG"
    return m.group(1)


def _white_png_with_strokes(tmp_path, name="sig.png", mode="RGBA"):
    p = tmp_path / name
    img = Image.new(mode, (400, 160), (255, 255, 255) if mode == "RGB" else (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    d.line([(20, 120), (120, 40), (220, 120), (320, 50)], fill=(0, 0, 0), width=6)
    img.save(p)
    return p


def test_registered():
    assert styles.get("esign.signature") is STYLE


def test_default_id_is_32_upper_hex():
    svg = STYLE.build_svg(**STYLE.DEFAULTS).svg
    assert re.fullmatch(r"[0-9A-F]{32}", _id_text(svg))


def test_default_uses_no_file_io(monkeypatch):
    """The 'sample' default must be GENERATED, never read from disk (PII-safe)."""
    def boom(*a, **k):
        raise AssertionError("Image.open must not be called on the sample path")
    monkeypatch.setattr(sig_mod.Image, "open", boom)
    result = STYLE.build_svg()  # all defaults -> signature='sample'
    assert "data:image/png;base64," in result.svg
    assert result.normalized_params["signature_mode"] == "sample"


def test_image_pipeline_roundtrip(tmp_path):
    p = _white_png_with_strokes(tmp_path)
    r1 = STYLE.build_svg(signature=str(p), name="Ada Lovelace")
    r2 = STYLE.build_svg(signature=str(p), name="Ada Lovelace")
    assert r1.svg == r2.svg, "same inputs must give byte-identical SVG"
    assert "data:image/png;base64," in r1.svg
    assert r1.normalized_params["signature_mode"] == "image"
    png = raster.render_png(
        r1.svg, font_files=[fp.file_path for fp in r1.fonts_used],
        width=420, background="transparent", skip_system_fonts=True,
    )
    assert png.startswith(PNG_MAGIC) and len(png) > 1000


def test_embedded_png_is_metadata_free(tmp_path):
    """No tIME/tEXt/pHYs/iCCP chunks — the determinism guard."""
    p = _white_png_with_strokes(tmp_path)
    png = _embedded_png(STYLE.build_svg(signature=str(p), name="X").svg)
    for chunk in (b"tIME", b"tEXt", b"iTXt", b"pHYs", b"iCCP"):
        assert chunk not in png, f"unexpected {chunk!r} chunk breaks determinism"


def test_white_knockout_makes_corner_transparent(tmp_path):
    p = _white_png_with_strokes(tmp_path)
    png = _embedded_png(STYLE.build_svg(signature=str(p), name="X").svg)
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    assert im.getpixel((0, 0))[3] == 0, "white background should be transparent"
    # Some pixel must remain opaque (the ink survived).
    assert im.getchannel("A").getextrema()[1] == 255


def test_jpg_input_knocked_out(tmp_path):
    p = _white_png_with_strokes(tmp_path, name="sig.jpg", mode="RGB")
    r = STYLE.build_svg(signature=str(p), name="X")
    im = Image.open(io.BytesIO(_embedded_png(r.svg))).convert("RGBA")
    assert im.getpixel((0, 0))[3] == 0


def test_recolor_match_paints_accent(tmp_path):
    p = _white_png_with_strokes(tmp_path)
    r = STYLE.build_svg(signature=str(p), name="X", color="red", sig_color="match")
    im = Image.open(io.BytesIO(_embedded_png(r.svg))).convert("RGBA")
    opaque = [(x, y) for x in range(im.width) for y in range(im.height)
              if im.getpixel((x, y))[3] > 200]
    assert opaque, "expected opaque ink pixels"
    x, y = opaque[len(opaque) // 2]
    assert im.getpixel((x, y))[:3] == (255, 0, 0)  # 'red' -> #FF0000


def test_auto_keeps_original_ink(tmp_path):
    p = _white_png_with_strokes(tmp_path)
    r = STYLE.build_svg(signature=str(p), name="X", color="blue")  # sig_color auto
    im = Image.open(io.BytesIO(_embedded_png(r.svg))).convert("RGBA")
    opaque = [im.getpixel((x, y)) for x in range(im.width) for y in range(im.height)
              if im.getpixel((x, y))[3] > 200]
    # Original ink is black-ish, not the blue accent.
    assert any(px[2] < 80 for px in opaque)


def test_blank_image_raises(tmp_path):
    p = tmp_path / "blank.png"
    Image.new("RGBA", (200, 100), (255, 255, 255, 255)).save(p)
    with pytest.raises(ValueError, match="blank"):
        STYLE.build_svg(signature=str(p), name="X")


def test_missing_path_raises():
    with pytest.raises(ValueError, match="not found"):
        STYLE.build_svg(signature="/no/such/signature.png", name="X")


def test_sig_id_override_verbatim_normalized():
    raw = "EB1CA841-4D13-478E-D6A3-FCAEC3D6548E"  # dashes tolerated
    r = STYLE.build_svg(name="X", sig_id=raw)
    assert _id_text(r.svg) == "EB1CA8414D13478ED6A3FCAEC3D6548E"
    assert not r.warnings


def test_sig_id_nonhex_hashed_with_warning():
    r = STYLE.build_svg(name="X", sig_id="contract-42")
    assert re.fullmatch(r"[0-9A-F]{32}", _id_text(r.svg))
    assert any("not 32 hex" in w for w in r.warnings)
    # stable across builds
    assert _id_text(r.svg) == _id_text(STYLE.build_svg(name="X", sig_id="contract-42").svg)


def test_id_changes_with_signer_and_image(tmp_path):
    p = _white_png_with_strokes(tmp_path)
    a = _id_text(STYLE.build_svg(signature=str(p), name="Alice").svg)
    b = _id_text(STYLE.build_svg(signature=str(p), name="Bob").svg)
    assert a != b, "different signers must yield different IDs"


@pytest.mark.parametrize("bracket", ["round", "square", "full", "none"])
def test_bracket_variants_render(bracket):
    r = STYLE.build_svg(bracket=bracket)
    svg = r.svg
    if bracket == "round":
        assert "A 16 16" in svg
    elif bracket == "square":
        assert "A 16 16" not in svg and "<path" in svg
    elif bracket == "full":
        assert "<rect" in svg
    else:  # none
        assert "<path" not in svg and "<rect" not in svg
    png = raster.render_png(svg, font_files=[fp.file_path for fp in r.fonts_used],
                            width=420, background="white", skip_system_fonts=True)
    assert png.startswith(PNG_MAGIC) and len(png) > 1000


def test_fonts_used_covers_named_families():
    r = STYLE.build_svg()
    families = {fp.family for fp in r.fonts_used}
    for fam in re.findall(r'font-family="([^"]+)"', r.svg):
        assert fam in families, f"font-family {fam!r} not pinned in fonts_used"


def test_huge_image_downscaled(tmp_path):
    p = tmp_path / "huge.png"
    img = Image.new("RGBA", (4000, 1500), (255, 255, 255, 255))
    ImageDraw.Draw(img).line([(50, 750), (3900, 750)], fill=(0, 0, 0), width=30)
    img.save(p)
    r = STYLE.build_svg(signature=str(p), name="X", max_px=1600)
    assert max(r.normalized_params["image_px"]) <= 1600
    assert any("downscaled" in w for w in r.warnings)


def test_typed_mode_pins_cursive_font():
    from stamp_cli.core.fonts import FontMissingError, default_resolver
    try:
        default_resolver.resolve("script")
    except FontMissingError:
        pytest.skip("no cursive font available on this host")
    r = STYLE.build_svg(signature="typed", name="Ada Lovelace")
    assert r.normalized_params["signature_mode"] == "typed"
    assert r.normalized_params["script_font"]
    assert "data:image/png;base64," not in r.svg  # text, not an image
    # the cursive family is both pinned and named in the SVG
    assert r.normalized_params["script_font"] in {fp.family for fp in r.fonts_used}
    assert f'font-family="{r.normalized_params["script_font"]}"' in r.svg
    # render exactly as production does (only pinned fonts) so a family-name
    # mismatch against the actual font file would surface as an empty render.
    png = raster.render_png(
        r.svg, font_files=[fp.file_path for fp in r.fonts_used],
        width=420, background="white", skip_system_fonts=True,
    )
    assert png.startswith(PNG_MAGIC) and len(png) > 1000


def _band_ink_px(svg, fonts_used):
    """Render exactly as production does and count ink pixels in the signature band."""
    png = raster.render_png(
        svg, font_files=[fp.file_path for fp in fonts_used],
        width=420, background="white", skip_system_fonts=True,
    )
    im = Image.open(io.BytesIO(png)).convert("RGB")
    band = im.crop((28, 50, 396, 154))  # the signature band in viewBox units (1:1 at width 420)
    data = band.tobytes()  # RGB, 3 bytes/px
    return sum(1 for i in range(0, len(data), 3)
               if min(data[i], data[i + 1], data[i + 2]) < 200)


@pytest.mark.skipif(
    not __import__("pathlib").Path("/System/Library/Fonts/Supplemental/SnellRoundhand.ttc").exists(),
    reason="Snell Roundhand (macOS) not present",
)
def test_typed_font_by_path_renders_ink():
    """A cursive font given by PATH must render (real OpenType family, not stem)."""
    ttc = "/System/Library/Fonts/Supplemental/SnellRoundhand.ttc"
    r = STYLE.build_svg(signature="typed", name="Ada Lovelace", script_font=ttc)
    # The emitted family must be the real name-table family, not the file stem.
    assert "SnellRoundhand" not in r.svg and "Snell Roundhand" in r.svg
    assert _band_ink_px(r.svg, r.fonts_used) > 300, "signature band rendered blank"


def test_icc_profile_stripped_and_id_invariant(tmp_path):
    """ICC-profiled inputs must not leak iCCP, and the ID must ignore the profile."""
    ImageCms = pytest.importorskip("PIL.ImageCms")
    base = tmp_path / "noicc.png"
    iccf = tmp_path / "icc.png"
    img = Image.new("RGB", (400, 160), (255, 255, 255))
    ImageDraw.Draw(img).line([(20, 120), (200, 40), (360, 120)], fill=(0, 0, 0), width=6)
    img.save(base)
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    img.save(iccf, icc_profile=profile)

    r_icc = STYLE.build_svg(signature=str(iccf), name="X")
    assert b"iCCP" not in _embedded_png(r_icc.svg), "ICC profile leaked into embedded PNG"
    # Same pixels, profile present vs absent → same content-hash ID.
    r_plain = STYLE.build_svg(signature=str(base), name="X")
    assert _id_text(r_icc.svg) == _id_text(r_plain.svg)


def test_cjk_label_pins_fallback_font():
    """A non-Latin label must pin a CJK fallback (or warn if none) — no silent tofu."""
    from stamp_cli.core.fonts import default_resolver
    r = STYLE.build_svg(label="已签署文件")
    has_cjk_font = any(fp.supports_cjk for fp in r.fonts_used)
    if default_resolver.first_available(("song", "hei", "ping", "hiragino")):
        assert has_cjk_font, "CJK label should pin a CJK fallback into fonts_used"
    else:
        assert any("CJK" in w or "boxes" in w for w in r.warnings)


def test_typed_id_tracks_font_and_ink():
    """Same name, different cursive appearance → different auto ID (Codex #2)."""
    from stamp_cli.core.fonts import FontMissingError, default_resolver
    try:
        default_resolver.resolve("script")
    except FontMissingError:
        pytest.skip("no cursive font available on this host")
    base = _id_text(STYLE.build_svg(signature="typed", name="Ada Lovelace").svg)
    other_ink = _id_text(STYLE.build_svg(signature="typed", name="Ada Lovelace",
                                         sig_color="red").svg)
    assert base != other_ink

"""Rendered-pixel precision checks for measured seal text geometry."""

from __future__ import annotations

import importlib
import io
import json
import math
import xml.etree.ElementTree as ET

import pytest
from click.testing import CliRunner
from PIL import Image, ImageChops

from stamp_cli import styles
from stamp_cli.core import export, raster
from stamp_cli.examples import SAMPLES


cli = importlib.import_module("stamp_cli.cli").cli
SVG_URI = "http://www.w3.org/2000/svg"
SVG_NS = f"{{{SVG_URI}}}"
ET.register_namespace("", SVG_URI)

CIRCLE_CENTER = (210.0, 210.0)
CIRCLE_INNER_FACING_EDGE = 136.0
CIRCLE_OUTER_FACING_EDGE = 188.25
CIRCLE_ANNULUS_MIDPOINT = 162.125
ALPHA_THRESHOLD = 32
RENDER_SCALE = 4


def _contains_svg_text(node: ET.Element) -> bool:
    return any(descendant.tag == f"{SVG_NS}text" for descendant in node.iter())


def _isolate_text(svg: str, href: str | None = None) -> str:
    """Remove painted shapes and unwanted text while retaining referenced defs."""
    root = ET.fromstring(svg)
    target_id = href.removeprefix("#") if href else None
    for child in list(root):
        if child.tag == f"{SVG_NS}defs":
            if target_id:
                for definition in list(child):
                    if definition.get("id") != target_id:
                        child.remove(definition)
                if not list(child):
                    root.remove(child)
            continue
        if not _contains_svg_text(child):
            root.remove(child)
            continue
        if href and not any(
            descendant.tag == f"{SVG_NS}textPath"
            and descendant.get("href") == href
            for descendant in child.iter()
        ):
            root.remove(child)
    return ET.tostring(root, encoding="unicode")


def _render_alpha(
    svg: str,
    result,
    *,
    scale: int = RENDER_SCALE,
    font_files: list[str] | None = None,
) -> Image.Image:
    png = raster.render_png(
        svg,
        font_files=(
            [font.file_path for font in result.fonts_used]
            if font_files is None
            else font_files
        ),
        width=round(result.view_box[2] * scale),
        background="transparent",
        skip_system_fonts=True,
    )
    with Image.open(io.BytesIO(png)) as rendered:
        alpha = rendered.convert("RGBA").getchannel("A")
        return alpha.point(lambda value: 255 if value >= ALPHA_THRESHOLD else 0)


def _isolate_element(svg: str, tag: str, **attributes: str) -> str:
    root = ET.fromstring(svg)
    qualified_tag = f"{SVG_NS}{tag}"
    for child in list(root):
        if child.tag != qualified_tag or any(
            child.get(key) != value for key, value in attributes.items()
        ):
            root.remove(child)
    return ET.tostring(root, encoding="unicode")


def _isolate_horizontal_text(svg: str) -> str:
    root = ET.fromstring(svg)
    for child in list(root):
        has_text = _contains_svg_text(child)
        has_text_path = any(
            descendant.tag == f"{SVG_NS}textPath" for descendant in child.iter()
        )
        if not has_text or has_text_path:
            root.remove(child)
    return ET.tostring(root, encoding="unicode")


def _bbox_in_svg(alpha: Image.Image, result) -> tuple[float, float, float, float]:
    bbox = alpha.getbbox()
    assert bbox is not None, "isolated element must produce visible ink"
    min_x, min_y, width, height = result.view_box
    scale_x = alpha.width / width
    scale_y = alpha.height / height
    return (
        min_x + bbox[0] / scale_x,
        min_y + bbox[1] / scale_y,
        min_x + bbox[2] / scale_x,
        min_y + bbox[3] / scale_y,
    )


def _assert_alpha_inside_ellipse(
    alpha: Image.Image,
    result,
    *,
    center: tuple[float, float],
    radii: tuple[float, float],
) -> None:
    bbox = alpha.getbbox()
    assert bbox is not None, "isolated text must produce visible ink"
    min_x, min_y, width, height = result.view_box
    scale_x = alpha.width / width
    scale_y = alpha.height / height
    pixels = alpha.load()
    cx, cy = center
    rx, ry = radii
    worst = 0.0
    worst_point = None
    for pixel_y in range(bbox[1], bbox[3]):
        for pixel_x in range(bbox[0], bbox[2]):
            if not pixels[pixel_x, pixel_y]:
                continue
            svg_x = min_x + (pixel_x + 0.5) / scale_x
            svg_y = min_y + (pixel_y + 0.5) / scale_y
            distance = ((svg_x - cx) / rx) ** 2 + ((svg_y - cy) / ry) ** 2
            if distance > worst:
                worst = distance
                worst_point = (svg_x, svg_y)
    assert worst <= 1.0, {"ellipse_distance": worst, "point": worst_point}


def _alpha_bbox_in_svg(svg: str, result) -> tuple[float, float, float, float]:
    alpha = _render_alpha(svg, result)
    return _bbox_in_svg(alpha, result)


def _circle_run_metrics(result, href: str, crown: str) -> dict[str, float]:
    alpha = _render_alpha(_isolate_text(result.svg, href), result)
    bbox = alpha.getbbox()
    assert bbox is not None, f"{href} must render visible ink"
    pixels = alpha.load()
    scale_x = alpha.width / result.view_box[2]
    scale_y = alpha.height / result.view_box[3]
    radial_min = math.inf
    radial_max = -math.inf
    angle_min = math.inf
    angle_max = -math.inf
    cx, cy = CIRCLE_CENTER

    for pixel_y in range(bbox[1], bbox[3]):
        for pixel_x in range(bbox[0], bbox[2]):
            if not pixels[pixel_x, pixel_y]:
                continue
            svg_x = result.view_box[0] + (pixel_x + 0.5) / scale_x
            svg_y = result.view_box[1] + (pixel_y + 0.5) / scale_y
            dx, dy = svg_x - cx, svg_y - cy
            radius = math.hypot(dx, dy)
            radial_min = min(radial_min, radius)
            radial_max = max(radial_max, radius)
            if crown == "top":
                angle = math.atan2(dx, -dy)
            else:
                angle = math.atan2(dx, dy)
            angle_min = min(angle_min, angle)
            angle_max = max(angle_max, angle)

    return {
        "radial_min": radial_min,
        "radial_max": radial_max,
        "radial_midpoint": (radial_min + radial_max) / 2,
        "angular_left": angle_min,
        "angular_right": angle_max,
        "angular_imbalance": abs(abs(angle_min) - abs(angle_max)) * CIRCLE_ANNULUS_MIDPOINT,
    }


@pytest.mark.parametrize("company", ["ACME", "EXAMPLE COMPANY LIMITED"], ids=["short", "normal"])
@pytest.mark.parametrize("en_spacing", [0.0, 1.5, 3.0])
@pytest.mark.parametrize("weight", [400, 700])
def test_circle_top_english_ink_is_centered_between_facing_rings(
    company, en_spacing, weight
):
    circle = styles.get("hk.circle")
    result = circle.build_svg(
        en=company,
        star=False,
        en_spacing=en_spacing,
        weight=weight,
    )
    metrics = _circle_run_metrics(result, "#company-top", "top")

    assert result.normalized_params["english_letter_spacing"] == en_spacing
    assert metrics["radial_midpoint"] == pytest.approx(
        CIRCLE_ANNULUS_MIDPOINT, abs=2
    ), metrics
    assert metrics["radial_min"] >= CIRCLE_INNER_FACING_EDGE, metrics
    assert metrics["radial_max"] <= CIRCLE_OUTER_FACING_EDGE, metrics


@pytest.mark.parametrize(
    ("href", "crown"),
    [("#company-top", "top"), ("#company-bottom", "bottom")],
)
def test_symmetric_top_and_bottom_runs_are_radially_and_angularly_centered(href, crown):
    circle = styles.get("hk.circle")
    result = circle.build_svg(
        en="AAAAAAAAA",
        en_bottom="AAAAAAAAA",
        star=False,
        en_spacing=1.5,
        en_bottom_spacing=1.5,
    )
    metrics = _circle_run_metrics(result, href, crown)

    assert metrics["radial_midpoint"] == pytest.approx(
        CIRCLE_ANNULUS_MIDPOINT, abs=2
    ), metrics
    assert metrics["radial_min"] >= CIRCLE_INNER_FACING_EDGE, metrics
    assert metrics["radial_max"] <= CIRCLE_OUTER_FACING_EDGE, metrics
    assert metrics["angular_imbalance"] <= 2, metrics


def test_circle_and_oval_spacing_options_are_in_cli_schema():
    response = CliRunner().invoke(cli, ["agent-info", "--json"])
    assert response.exit_code == 0, response.output
    manifest = json.loads(response.stdout)
    schemas = {style["id"]: style["params"] for style in manifest["styles"]}

    for style_id in ("hk.circle", "hk.oval"):
        assert schemas[style_id]["en_spacing"]["type"] == "number"
        assert schemas[style_id]["en_spacing"].get("default") is None
        assert schemas[style_id]["zh_spacing"]["type"] == "number"
        assert schemas[style_id]["zh_spacing"]["default"] == 1.0


@pytest.mark.parametrize(
    ("style_id", "command"),
    [
        (
            "hk.circle",
            ["hk", "circle", "--en", "EXAMPLE COMPANY", "--zh-line1", "示例公司"],
        ),
        (
            "hk.oval",
            ["hk", "oval", "--en", "EXAMPLE COMPANY", "--zh-line1", "示例公司"],
        ),
    ],
)
def test_cli_zero_spacing_is_preserved_and_distinct_from_defaults(
    tmp_path, style_id, command
):
    output = tmp_path / f"{style_id}.svg"
    response = CliRunner().invoke(
        cli,
        [
            *command,
            "--en-spacing", "0",
            "--zh-spacing", "0",
            "--output", str(output),
            "--json",
        ],
    )
    assert response.exit_code == 0, response.output
    envelope = json.loads(response.stdout)
    normalized = envelope["normalized_params"]
    assert normalized["english_letter_spacing"] == 0
    assert normalized["chinese_letter_spacing"] == 0

    style = styles.get(style_id)
    params = {"en": "EXAMPLE COMPANY", "zh_line1": "示例公司"}
    default = style.build_svg(**params)
    zero = style.build_svg(**params, en_spacing=0, zh_spacing=0)
    assert default.normalized_params["english_letter_spacing"] == 1.5
    assert default.normalized_params["chinese_letter_spacing"] == 1.0
    assert zero.svg != default.svg


@pytest.mark.parametrize(
    ("style_id", "command"),
    [
        (
            "hk.circle",
            ["hk", "circle", "--en", "EXAMPLE COMPANY", "--zh-line1", "示例公司"],
        ),
        (
            "hk.oval",
            ["hk", "oval", "--en", "EXAMPLE COMPANY", "--zh-line1", "示例公司"],
        ),
    ],
)
@pytest.mark.parametrize("option", ["--en-spacing", "--zh-spacing"])
@pytest.mark.parametrize("bad_value", ["-0.1", "nan"], ids=["negative", "nonfinite"])
def test_cli_rejects_invalid_spacing(tmp_path, style_id, command, option, bad_value):
    output = tmp_path / f"{style_id}-{option.removeprefix('--')}-{bad_value}.svg"
    response = CliRunner().invoke(
        cli,
        [*command, option, bad_value, "--output", str(output), "--json"],
    )

    assert response.exit_code == 1
    error = json.loads(response.stdout)
    assert error["ok"] is False
    assert error["exit_code"] == 1
    if bad_value == "nan":
        assert "finite" in error["error"].lower()
    else:
        assert "spacing" in error["error"].lower()
    assert not output.exists()


@pytest.mark.parametrize(
    "style_id", ["prc.legal_rep", "prc.foreign_invested_oval"]
)
def test_default_legal_and_horizontal_bilingual_text_block_is_canvas_centered(style_id):
    style = styles.get(style_id)
    result = style.build_svg(**SAMPLES[style_id])
    if style_id == "prc.legal_rep":
        assert result.normalized_params["label"]
    else:
        assert result.normalized_params["layout"] == "horizontal"
        assert result.normalized_params["en"]

    text_only = _isolate_text(result.svg)
    left, top, right, bottom = _alpha_bbox_in_svg(text_only, result)
    min_x, min_y, width, height = result.view_box
    expected_center = (min_x + width / 2, min_y + height / 2)
    measured_center = ((left + right) / 2, (top + bottom) / 2)

    assert measured_center[0] == pytest.approx(expected_center[0], abs=2), {
        "bbox": (left, top, right, bottom),
        "measured_center": measured_center,
        "expected_center": expected_center,
    }
    assert measured_center[1] == pytest.approx(expected_center[1], abs=2), {
        "bbox": (left, top, right, bottom),
        "measured_center": measured_center,
        "expected_center": expected_center,
    }


@pytest.mark.parametrize("style_id", ["hk.circle", "hk.oval"])
def test_star_toggle_adds_centered_outlined_bottom_floret_without_font_fallback(style_id):
    style = styles.get(style_id)
    params = {"en": "EXAMPLE COMPANY LIMITED", "zh_line1": "示例有限公司"}
    with_floret = style.build_svg(**params, star=True)
    without_floret = style.build_svg(**params, star=False)

    common_fonts = [font.file_path for font in with_floret.fonts_used]
    difference = ImageChops.difference(
        _render_alpha(with_floret.svg, with_floret, font_files=common_fonts),
        _render_alpha(without_floret.svg, without_floret, font_files=common_fonts),
    )
    left, top, right, bottom = _bbox_in_svg(difference, with_floret)
    min_x, min_y, width, height = with_floret.view_box
    cx, cy = min_x + width / 2, min_y + height / 2
    arc_ry = with_floret.normalized_params["arc_ink_center_radii"][1]
    assert (left + right) / 2 == pytest.approx(cx, abs=1)
    assert (top + bottom) / 2 == pytest.approx(cy + arc_ry, abs=1)

    outlined_floret = _isolate_element(
        with_floret.svg, "path", **{"aria-label": "❋"}
    )
    assert _render_alpha(
        outlined_floret, with_floret, font_files=[]
    ).getbbox() is not None


@pytest.mark.parametrize("prc_star_size", [10, 14])
@pytest.mark.parametrize(
    ("zh_line1", "zh_line2"),
    [("示例有限公司", ""), ("示例有限公司", "合同專用章")],
    ids=["one-line", "two-lines"],
)
def test_circle_chinese_labels_clear_central_star_and_inner_ellipse(
    prc_star_size, zh_line1, zh_line2
):
    result = styles.get("hk.circle").build_svg(
        zh_line1=zh_line1,
        zh_line2=zh_line2,
        prc_star=True,
        prc_star_size=prc_star_size,
        star=False,
    )
    text_alpha = _render_alpha(_isolate_horizontal_text(result.svg), result)
    star_alpha = _render_alpha(_isolate_element(result.svg, "polygon"), result)

    assert text_alpha.getbbox() is not None
    assert star_alpha.getbbox() is not None
    assert ImageChops.multiply(text_alpha, star_alpha).getbbox() is None
    _assert_alpha_inside_ellipse(
        text_alpha,
        result,
        center=CIRCLE_CENTER,
        radii=(127, 127),
    )


@pytest.mark.parametrize("name", ["示例公司", "示例科技有限公司"])
def test_foreign_invested_curved_text_stays_safely_inside_inner_ellipse(name):
    result = styles.get("prc.foreign_invested_oval").build_svg(
        name=name,
        en="EXAMPLE COMPANY LIMITED",
        layout="curved",
    )
    assert result.normalized_params["layout"] == "curved"
    text_alpha = _render_alpha(_isolate_text(result.svg), result)

    _assert_alpha_inside_ellipse(
        text_alpha,
        result,
        center=(225, 150),
        radii=(207, 132),
    )


def test_hk_oval_long_two_line_chinese_block_stays_inside_safe_ellipse():
    result = styles.get("hk.oval").build_svg(
        en="EXAMPLE COMPANY LIMITED",
        zh_line1="示例國際生物科技有限公司",
        zh_line2="艾克米創新系統發展有限公司",
        star=False,
    )
    horizontal_text = _isolate_horizontal_text(result.svg)
    root = ET.fromstring(horizontal_text)
    assert len(root.findall(f"{SVG_NS}text")) == 2
    text_alpha = _render_alpha(horizontal_text, result)

    _assert_alpha_inside_ellipse(
        text_alpha,
        result,
        center=(240, 160),
        radii=(155, 77),
    )


def test_signature_only_ignores_hidden_long_label_but_classic_rejects_it():
    style = styles.get("esign.signature")
    label = "W" * 100

    bare = style.build_svg(
        signature="sample",
        layout="signature-only",
        label=label,
    )
    assert label not in bare.svg
    assert bare.normalized_params["label"] == label

    with pytest.raises(ValueError, match="fit legibly|Shorten"):
        style.build_svg(signature="sample", layout="classic", label=label)


def test_examples_cover_all_fourteen_synthetic_defaults():
    assert len(SAMPLES) == 14
    assert set(SAMPLES) == {style.META.id for style in styles.all()}


@pytest.mark.parametrize(("style_id", "params"), SAMPLES.items(), ids=SAMPLES)
def test_synthetic_default_renders_unclipped_at_300_dpi(style_id, params):
    style = styles.get(style_id)
    result = style.build_svg(**params)
    width_mm, height_mm, pixel_width, _actual_dpi = export.dimensions(
        result, dpi=300
    )
    source = export.prepare_svg(
        result,
        width_mm=width_mm,
        height_mm=height_mm,
        background="transparent",
    )
    png = raster.render_png(
        source,
        font_files=[font.file_path for font in result.fonts_used],
        width=pixel_width,
        background="transparent",
        skip_system_fonts=True,
    )

    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(io.BytesIO(png)) as rendered:
        alpha = rendered.convert("RGBA").getchannel("A")
        bbox = alpha.point(lambda value: 255 if value >= 16 else 0).getbbox()
        dimensions = rendered.size
    assert bbox is not None, style_id
    assert 0 < bbox[0] < bbox[2] < dimensions[0], (style_id, bbox, dimensions)
    assert 0 < bbox[1] < bbox[3] < dimensions[1], (style_id, bbox, dimensions)


def test_long_top_and_bottom_arcs_keep_clear_shoulder_gaps():
    result = styles.get('hk.circle').build_svg(
        en='EXAMPLE RESEARCH AND TECHNOLOGY LIMITED',
        en_bottom='AUTHORISED BUSINESS DOCUMENTS AND AGREEMENTS',
        zh_line1='示例有限公司',
    )
    top = _alpha_bbox_in_svg(_isolate_text(result.svg, '#company-top'), result)
    bottom = _alpha_bbox_in_svg(_isolate_text(result.svg, '#company-bottom'), result)
    assert bottom[1] - top[3] >= 8, (top, bottom)


def test_three_full_width_bilingual_rows_stay_inside_safe_ellipse():
    result = styles.get('prc.foreign_invested_oval').build_svg(
        name='示例科技', name_line2='國際發展有限公司',
        en='EXAMPLE INTERNATIONAL LIMITED',
    )
    _assert_alpha_inside_ellipse(
        _render_alpha(_isolate_text(result.svg), result), result,
        center=(225, 150), radii=(207, 132),
    )


def test_tall_scan_keeps_ink_height_and_reference_across_signature_layouts(tmp_path):
    from PIL import ImageDraw
    source = tmp_path / 'synthetic-tall.png'
    scan = Image.new('RGB', (500, 1200), 'white')
    ImageDraw.Draw(scan).line([(180, 1000), (240, 200), (320, 1050)], fill='black', width=10)
    scan.save(source)
    references, heights = set(), []
    for layout in ('classic', 'clean', 'signature-only'):
        result = styles.get('esign.signature').build_svg(
            signature=str(source), name='Sample Signer', layout=layout,
        )
        references.add(result.normalized_params['sig_id'])
        ink = _isolate_element(result.svg, 'image')
        left, top, right, bottom = _alpha_bbox_in_svg(ink, result)
        heights.append(bottom - top)
        assert 0 < left < right < result.view_box[2]
        assert 0 < top < bottom < result.view_box[3]
    assert len(references) == 1
    assert max(heights) - min(heights) <= .5
    assert min(heights) > 225

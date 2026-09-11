"""Boundary regressions for measured company and personal seal layouts."""

from __future__ import annotations

import importlib
import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from click.testing import CliRunner
from PIL import Image, ImageFont

from stamp_cli import styles
from stamp_cli.core import raster


cli = importlib.import_module("stamp_cli.cli").cli
HK_RECT = styles.get("hk.rect")
HK_OVAL = styles.get("hk.oval")
NAME_CHOP = styles.get("personal.name_chop")
SVG_NS = "{http://www.w3.org/2000/svg}"


def test_hk_rect_explicit_empty_signature_fields_override_sign_preset():
    result = HK_RECT.build_svg(
        preset="sign",
        line1="Example Systems Limited",
        line2="示例系統有限公司",
        signature_top="",
        signature_bottom="",
        signature_line=False,
    )

    assert result.normalized_params["signature_top"] == ""
    assert result.normalized_params["signature_bottom"] == ""
    assert result.normalized_params["signature_line"] is False
    assert "For and on behalf of" not in result.svg
    assert "Authorised signature" not in result.svg
    assert "stroke-dasharray" not in result.svg


def test_hk_rect_ten_line_address_grows_canvas_within_painted_bounds():
    base = HK_RECT.build_svg(
        preset="address",
        line1="Example Systems Limited",
        line2="One Example Road",
    )
    address = "\n".join(f"Address line {number}" for number in range(1, 11))
    result = HK_RECT.build_svg(
        preset="address",
        line1="Example Systems Limited",
        line2=address,
    )

    assert result.view_box[3] > base.view_box[3]
    assert result.view_box[3] < 600
    assert result.svg.count("<text ") == 11

    x, y, width, height = result.view_box
    px, py, pwidth, pheight = result.painted_bbox
    assert x <= px and y <= py
    assert px + pwidth <= x + width
    assert py + pheight <= y + height

    png = raster.render_png(
        result.svg,
        font_files=[font.file_path for font in result.fonts_used],
        width=720,
        background="transparent",
        skip_system_fonts=True,
    )
    with Image.open(io.BytesIO(png)) as rendered:
        bbox = rendered.convert("RGBA").getchannel("A").getbbox()
        scale = rendered.width / width
    assert bbox is not None
    assert bbox[0] >= int(px * scale) - 2
    assert bbox[1] >= int(py * scale) - 2
    assert bbox[2] <= int((px + pwidth) * scale) + 2
    assert bbox[3] <= int((py + pheight) * scale) + 2


def test_hk_oval_rejects_unreadable_two_hundred_character_company_name():
    company = ("Example Company " * 20)[:200]
    assert len(company) == 200
    with pytest.raises(ValueError, match="too long to fit legibly"):
        HK_OVAL.build_svg(en=company, zh_line1="示例公司")


def test_normal_name_chop_export_has_transparent_paper_and_glyphs_inside_frame(tmp_path):
    output = tmp_path / "synthetic-name-chop.svg"
    invocation = CliRunner().invoke(
        cli,
        [
            "personal", "name-chop", "--chars", "陳大文",
            "--output", str(output), "--format", "svg", "--json",
        ],
    )
    assert invocation.exit_code == 0, invocation.output
    envelope = json.loads(invocation.stdout)
    assert envelope["background"] == "transparent"
    assert Path(envelope["paths"]["svg"]) == output

    root = ET.fromstring(output.read_bytes())
    frame = root.find(f"{SVG_NS}rect")
    assert frame is not None
    assert frame.attrib["fill"] == "none"

    built = NAME_CHOP.build_svg(chars="陳大文")
    profile = built.fonts_used[0]
    texts = root.findall(f".//{SVG_NS}text")
    assert len(texts) == 3
    for text in texts:
        size = float(text.attrib["font-size"])
        face = ImageFont.truetype(
            profile.file_path, size * 4, index=profile.face_index
        )
        left, top, right, bottom = (
            value / 4 for value in face.getbbox(text.text or "", anchor="ls")
        )
        x, y = float(text.attrib["x"]), float(text.attrib["y"])
        assert 18 <= x + left <= x + right <= 142
        assert 18 <= y + top <= y + bottom <= 142

    png = raster.render_png(
        output.read_text(encoding="utf-8"),
        font_files=[profile.file_path],
        width=800,
        background="transparent",
        skip_system_fonts=True,
    )
    with Image.open(io.BytesIO(png)) as rendered:
        assert rendered.convert("RGBA").getpixel((0, 0))[3] == 0

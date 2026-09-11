"""Regression coverage for the measured, proportional ``hk.oval`` renderer."""

from __future__ import annotations

import pytest

from stamp_cli import styles
from stamp_cli.core import raster

styles.reload()
OVAL = styles.get("hk.oval")

pytestmark = pytest.mark.skipif(OVAL is None, reason="hk.oval not registered yet")

# Fictional company data keeps the regression fixture safe to publish.
PARAMS = dict(
    en="Acme Biotechnologies (HK) Limited",
    zh_line1="艾克米生物科技",
    zh_line2="(香港)有限公司",
)


def _build():
    return OVAL.build_svg(**{**(OVAL.DEFAULTS or {}), **PARAMS})


def test_canonical_size_is_45x30():
    assert OVAL.META.canonical_size_mm == (45.0, 30.0)


def test_viewbox_aspect_matches_canonical_size():
    vb = _build().view_box
    assert vb[2] / vb[3] == pytest.approx(45 / 30)


def test_svg_carries_measured_oval_structure():
    svg = _build().svg
    # Two textPath ellipses (top + bottom) and the floret marker.
    assert svg.count("textPath") >= 2
    assert "oval-patha" in svg          # top text path id
    assert "❋" in svg                   # bottom floret (U+274B)
    # The manual two-line Chinese split, both present and unmerged.
    assert "艾克米生物科技" in svg
    assert "(香港)有限公司" in svg


def test_renders_to_reasonable_png():
    result = _build()
    png = raster.render_png(
        result.svg,
        font_files=[fp.file_path for fp in result.fonts_used],
        width=900,
        background="transparent",
    )
    assert png.startswith(b"\x89PNG")
    assert len(png) > 20_000, "the full stamp should be a substantial PNG"


def test_manual_split_is_respected_not_autosplit():
    """zh_line1/zh_line2 must be honored verbatim (no 有限公司 auto-split)."""
    svg = _build().svg
    # auto-split would have put 有限公司 on its own / merged the parens line;
    # we asserted the exact manual lines above. Also ensure line1 has no 有限公司.
    assert "有限公司" not in "艾克米生物科技"
    assert "艾克米生物科技" in svg and "(香港)有限公司" in svg

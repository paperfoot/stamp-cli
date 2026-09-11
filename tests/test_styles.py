"""Registry-driven style tests.

These parametrize over every *registered* style, so the suite automatically
grows as new style modules land (the build-stamp-cli fan-out). Each style must:
  - satisfy the StyleSpec protocol + carry complete metadata,
  - build a non-empty SVG StyleResult from its defaults,
  - rasterize to a real PNG.
"""

from __future__ import annotations

import pytest

from stamp_cli import styles
from stamp_cli.core import raster
from stamp_cli.styles.base import StyleResult, StyleSpec

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Collect once at import. reload() ensures we see everything on disk now.
styles.reload()
ALL = styles.all()
IDS = [s.META.id for s in ALL]


def _sample_params(spec) -> dict:
    """Use the same valid, fictional examples exposed by preview and manifest."""
    from stamp_cli.examples import SAMPLES
    return dict(SAMPLES[spec.META.id])


def test_registry_loaded_without_errors():
    errs = styles.load_errors()
    assert not errs, "style modules failed to import:\n" + "\n".join(
        f"  {e.module}: {e.error}" for e in errs
    )


def test_at_least_hk_oval_registered():
    assert "hk.oval" in IDS


@pytest.mark.skipif(not ALL, reason="no styles registered yet")
@pytest.mark.parametrize("spec", ALL, ids=IDS)
def test_style_satisfies_protocol_and_metadata(spec):
    assert isinstance(spec, StyleSpec)
    m = spec.META
    assert m.id and "." in m.id, "id should be '<country>.<shape>'"
    assert m.country and m.shape and m.title and m.description and m.reference
    assert spec.PARAMS, "a style must declare PARAMS"


@pytest.mark.skipif(not ALL, reason="no styles registered yet")
@pytest.mark.parametrize("spec", ALL, ids=IDS)
def test_style_builds_svg(spec):
    result = spec.build_svg(**_sample_params(spec))
    assert isinstance(result, StyleResult)
    assert "<svg" in result.svg and "</svg>" in result.svg
    assert len(result.view_box) == 4
    assert result.style_id == spec.META.id
    assert result.fonts_used, "build_svg must pin the fonts it used"


@pytest.mark.skipif(not ALL, reason="no styles registered yet")
@pytest.mark.parametrize("spec", ALL, ids=IDS)
def test_style_rasterizes_to_png(spec):
    result = spec.build_svg(**_sample_params(spec))
    png = raster.render_png(
        result.svg,
        font_files=[fp.file_path for fp in result.fonts_used],
        width=400,
        background="transparent",
    )
    assert png.startswith(PNG_MAGIC)
    assert len(png) > 1000, "suspiciously tiny PNG — likely an empty render"


@pytest.mark.skipif(not ALL, reason="no styles registered yet")
@pytest.mark.parametrize("spec", ALL, ids=IDS)
def test_build_svg_is_deterministic(spec):
    p = _sample_params(spec)
    assert spec.build_svg(**p).svg == spec.build_svg(**p).svg, (
        "same params must produce byte-identical SVG (golden-test prerequisite)"
    )

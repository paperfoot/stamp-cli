"""Regression tests for the build-verify findings (workflow wf_2e403ea1-6a4).

Each test pins a specific defect the adversarial verify phase caught, so a future
change can't silently reintroduce it.
"""

from __future__ import annotations

import pytest

from stamp_cli import styles

styles.reload()


# ── PRC round seals: radial CJK placement, not tangent textPath ───────────────
ROUND = ["prc.state_owned_round", "prc.company_round", "prc.department_round"]


@pytest.mark.parametrize("style_id", ROUND)
def test_round_name_is_radial_not_textpath(style_id):
    """The curved company name must be placed glyph-by-glyph with per-char
    rotation (upright/radial), NOT as a single Latin-style <textPath> that
    tangent-shears CJK characters onto their sides."""
    spec = styles.get(style_id)
    name = "上海示例創新科技有限公司"  # 13 chars
    svg = spec.build_svg(**{**spec.DEFAULTS, _name_param(spec): name}).svg
    # Each character gets its own rotate() transform → at least len(name) of them.
    assert svg.count("rotate(") >= len(name), f"{style_id}: name not radial"
    # The whole name must NOT ride a single textPath run.
    assert f">{name}<" not in svg


@pytest.mark.parametrize("style_id", ROUND)
def test_round_name_span_capped(style_id):
    """A long name must tighten within the upper band, never wrap past the cap
    down to the 3/9 o'clock side walls."""
    spec = styles.get(style_id)
    long_name = "北京长名称测试科技股份有限责任公司"  # 17 chars
    r = spec.build_svg(**{**spec.DEFAULTS, _name_param(spec): long_name})
    span = r.normalized_params.get("name_arc_span_deg")
    assert span is not None and span <= 210.0, f"{style_id}: span {span} too wide"


def test_state_owned_no_clip():
    """The name's outward extent must stay inside the inner border (the clipping
    bug: clearance must scale with font size)."""
    spec = styles.get("prc.state_owned_round")
    for name in ("九州科技公司", "上海示例創新科技有限公司",
                 "北京长名称测试科技股份有限责任公司"):
        np = spec.build_svg(name=name).normalized_params
        assert np["name_outer_extent"] < np["inner_clear_radius"], name


# ── prc.finance: delegates to department_round (single border, big star) ──────
def test_finance_single_border_and_star():
    spec = styles.get("prc.finance")
    r = spec.build_svg(company="上海示例創新科技有限公司")
    assert r.style_id == "prc.finance"
    # Department-round geometry: exactly one stroked ring circle, plus a star.
    assert r.svg.count("<circle") == 1, "finance should have a single border ring"
    assert "<polygon" in r.svg, "finance should carry the central star polygon"


# ── prc.foreign_invested_oval: no star ever; curved caps to horizontal ────────
def test_foreign_invested_never_has_star():
    spec = styles.get("prc.foreign_invested_oval")
    for layout in ("horizontal", "curved"):
        svg = spec.build_svg(name="示例公司", layout=layout).svg
        assert "<polygon" not in svg and "❋" not in svg


def test_foreign_invested_curved_falls_back_for_long_names():
    spec = styles.get("prc.foreign_invested_oval")
    r = spec.build_svg(name="上海示例創新科技有限公司", layout="curved")  # 13 chars
    assert any("horizontal" in w for w in r.warnings), "expected fallback warning"
    assert "fio-top" not in r.svg, "long curved name should not use the top arc path"


# ── western.text: repeatable lines render every line ──────────────────────────
def test_western_renders_all_lines():
    spec = styles.get("western.text")
    r = spec.build_svg(lines=["PAID", "2026-05-29"])
    assert "PAID" in r.svg and "2026-05-29" in r.svg


def _name_param(spec) -> str:
    """The company-name param differs across PRC styles (name vs company)."""
    names = {p.name for p in spec.PARAMS}
    return "name" if "name" in names else "company"

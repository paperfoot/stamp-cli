"""``prc.company_round`` — generic PRC limited-liability company round seal.

The everyday mainland 公章 (company seal) for a 有限责任公司: a single circular
border, a solid five-pointed red star in the centre, and the registered company
name curved evenly along the top arc in Songti (简化宋体). An optional bottom
label (e.g. a 13-digit registration number or a 专用章 designation) curves along
the bottom arc, upright.

This is the **40 mm** generic LLC variant. It is the same family as
``prc.state_owned_round`` (42 mm) but smaller, with a *lighter* (1 mm) border per
the limited-company convention rather than the 1.2 mm state-owned border.

Dimensions follow the seal-management convention recorded in
``reference_hk_seal_specs`` / PLAN.md §5–6:

* **Diameter** 40 mm (``canonical_size_mm = (40, 40)``).
* **Border** 1 mm wide ≈ 2.5 % of the diameter.
* **Central star** five-pointed, diameter ≈ 33 % of the seal (≈ 13.2 mm).
* **Font** Songti SC (``song`` alias) — the regulation's 简化宋体.

Geometry is laid out in an abstract 400-unit-diameter coordinate space centred on
the origin (``viewBox = -210 -210 420 420`` with a 10-unit margin). Real
millimetre sizing is applied downstream by the rasterizer from
``canonical_size_mm`` / ``--px-width`` — the SVG itself is resolution-independent,
exactly like ``hk.oval``.

Unlike the foreign-invested oval, the PRC star here is a **real five-point
``<polygon>``** (per the task contract), not a glyph — so it renders identically
regardless of which fonts a host has.
"""

from __future__ import annotations

import math

from ..base import ParamSpec, StyleMeta, StyleResult
from ...core import colors as colors_mod
from ...core import geometry, svg
from ...core.fonts import default_resolver

# Style schema version. Bump when geometry/defaults change in a way that would
# alter golden-hash output.
_VERSION = "1"

# Abstract layout space: a seal of diameter 400 units centred on the origin,
# with a 10-unit margin so the outer stroke is never clipped.
_R = 200.0  # outer seal radius (units); 40 mm maps onto a 400-unit diameter.
_MARGIN = 10.0
_VIEW_BOX: tuple[float, float, float, float] = (
    -(_R + _MARGIN),
    -(_R + _MARGIN),
    2 * (_R + _MARGIN),
    2 * (_R + _MARGIN),
)
_CX, _CY = 0.0, 0.0  # everything is centred on the origin

# Proportions (fractions of the *diameter*), from the LLC convention.
_BORDER_FRAC = 0.025   # 1 mm / 40 mm  → lighter than state-owned's 0.03
_STAR_FRAC = 0.33      # star diameter ≈ 33 % of the seal

# Arc the curved text sweeps (centred at the top / bottom). The company name on
# a real 公章 spreads across most of the upper circle; a bottom label is tighter.
_NAME_ARC_DEG = 250.0
_BOTTOM_ARC_DEG = 140.0


def _star_points(cx: float, cy: float, r_outer: float) -> str:
    """``points`` for an upright 5-point star centred at ``(cx, cy)``.

    ``r_outer`` is the circumradius (tip distance). The inner radius uses the
    canonical regular-pentagram ratio so the star reads as the standard 五角星.
    The first tip points straight up (angle -90°).
    """
    # Regular pentagram inner/outer radius ratio.
    r_inner = r_outer * math.sin(math.radians(18)) / math.sin(math.radians(54))
    pts: list[str] = []
    for k in range(5):
        # Outer tip.
        a_out = math.radians(-90 + 72 * k)
        pts.append(f"{svg.num(cx + r_outer * math.cos(a_out))},"
                   f"{svg.num(cy + r_outer * math.sin(a_out))}")
        # Inner vertex, halfway to the next tip.
        a_in = math.radians(-90 + 72 * k + 36)
        pts.append(f"{svg.num(cx + r_inner * math.cos(a_in))},"
                   f"{svg.num(cy + r_inner * math.sin(a_in))}")
    return " ".join(pts)


def _name_font_size(n: int) -> float:
    """Glyph point-size for an ``n``-character curved name.

    Units are the abstract 400-diameter space. Shorter names get larger glyphs;
    long names step down so they still fit the arc. Letter-spacing is computed
    separately (see :func:`_arc_letter_spacing`) so the name sweeps a fixed
    target arc regardless of length.
    """
    if n <= 0:
        return 0.0
    if n <= 6:
        return 42.0
    if n <= 9:
        return 36.0
    if n <= 12:
        return 32.0
    if n <= 15:
        return 28.0
    if n <= 18:
        return 24.0
    return 21.0


def _arc_letter_spacing(
    n: int, font_size: float, radius: float, arc_deg: float
) -> float:
    """Letter-spacing so ``n`` glyphs of ``font_size`` sweep ``arc_deg`` degrees.

    The text is centred at ``startOffset=50%``; resvg lays out each cluster
    along the path with ``advance = font_size + letter_spacing`` (it drops the
    spacing after the final cluster). To span an arc length of
    ``radius * arc_deg`` we solve ``(n-1)*(font_size+ls) + font_size = arc_len``
    for ``ls``. Clamped to a small non-negative minimum so short names stay
    readable and never overlap.
    """
    if n <= 1 or font_size <= 0:
        return 0.0
    arc_len = radius * math.radians(arc_deg)
    ls = (arc_len - n * font_size) / (n - 1)
    # Keep a sane band: never negative (resvg zeroes invalid negatives anyway),
    # and don't blow names apart past ~1.4× the glyph.
    return max(2.0, min(ls, font_size * 1.4))


class _PrcCompanyRound:
    META = StyleMeta(
        id="prc.company_round",
        country="prc",
        shape="circle",
        title="PRC company round seal (40mm LLC 公章)",
        description=(
            "Generic mainland limited-company round seal: single 1mm border, a "
            "solid five-pointed star in the centre (~33% of the seal), and the "
            "company name curved along the top arc in Songti. 40mm — the LLC "
            "variant of the 42mm state-owned seal, with a lighter border."
        ),
        canonical_size_mm=(40.0, 40.0),
        reference="PRC seal-management convention (国发〔1999〕25号); SealUtil layout",
    )

    PARAMS = [
        ParamSpec(
            name="company", type=str, default="", required=True,
            help="Registered company name, curved along the top arc "
                 "(e.g. 上海示例科技有限公司).",
        ),
        ParamSpec(
            name="bottom", type=str, default="",
            help="Optional bottom-arc text, upright (e.g. a 13-digit "
                 "registration number or a 专用章 designation). Empty by default "
                 "for the plain generic 公章.",
        ),
        ParamSpec(
            name="star", type=bool, default=True,
            help="Show the central five-pointed star.",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, blue, purple, black, vermilion…) or "
                 "#RRGGBB. PRC seals are conventionally red (#FF0000).",
        ),
        ParamSpec(
            name="weight", type=int, default=700,
            help="Font weight for the Chinese name (Songti reads heavy on a "
                 "seal; 700 by default).",
        ),
        ParamSpec(
            name="zh_font", type=str, default="song",
            help="Font alias for the Chinese text (default Songti SC — the "
                 "regulation's 简化宋体).",
        ),
    ]

    DEFAULTS = {
        "company": "",
        "bottom": "",
        "star": True,
        "color": "red",
        "weight": 700,
        "zh_font": "song",
    }

    def build_svg(self, **params) -> StyleResult:
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        warnings: list[str] = []

        company = str(p["company"]).strip()
        if not company:
            raise ValueError(
                "prc.company_round requires --company (the registered name)."
            )
        bottom = str(p["bottom"]).strip()
        show_star = bool(p["star"])

        try:
            weight = int(p["weight"])
        except (TypeError, ValueError):
            raise ValueError(f"--weight must be an integer, got {p['weight']!r}")

        fill = colors_mod.parse(str(p["color"]))

        # ── Fonts ─────────────────────────────────────────────────────────────
        zh_prof = default_resolver.resolve(str(p["zh_font"]))
        if not zh_prof.supports_cjk:
            warnings.append(
                f"Chinese font '{zh_prof.family}' may not cover CJK glyphs."
            )
        zh_family = zh_prof.family
        fonts_used = [zh_prof]

        n = svg.num

        # ── Geometry (fractions of the diameter) ──────────────────────────────
        diameter = 2 * _R
        border_w = _BORDER_FRAC * diameter            # 1 mm stroke
        # The stroke straddles the path; place the centreline so the stroke's
        # outer edge sits at the seal radius (border lives *inside* the disc).
        ring_r = _R - border_w / 2.0
        star_r = (_STAR_FRAC * diameter) / 2.0         # star circumradius

        # Top-arc name baseline: a textPath circle just inside the border, with
        # enough clearance for the glyph height. The name sweeps a wide arc (the
        # canonical 公章 spread) via computed letter-spacing.
        name_fs = _name_font_size(len(company))
        name_radius = ring_r - border_w / 2.0 - name_fs * 0.70

        # Bottom-arc label baseline (only when provided): a touch tighter, narrower
        # arc, smaller glyphs.
        bottom_fs = 0.0
        bottom_spacing = 0.0
        bottom_radius = 0.0
        if bottom:
            bottom_fs = _name_font_size(len(bottom)) * 0.78
            bottom_radius = ring_r - border_w / 2.0 - bottom_fs * 0.60
            bottom_spacing = _arc_letter_spacing(
                len(bottom), bottom_fs, bottom_radius, _BOTTOM_ARC_DEG
            )

        # ── Border ring (a stroked circle) ────────────────────────────────────
        border = (
            f'<circle cx="0" cy="0" r="{n(ring_r)}" fill="none" '
            f'stroke="{fill}" stroke-width="{n(border_w)}"/>'
        )

        # ── Central star (real polygon) ───────────────────────────────────────
        star_el = ""
        if show_star:
            star_el = (
                f'<polygon points="{_star_points(_CX, _CY, star_r)}" '
                f'fill="{fill}"/>'
            )

        # ── Company name — radial CJK placement (upright, feet inward) ────────
        # Cap the span at 200° so the name keeps the upper band and never reaches
        # the bottom label (200/2 + 140/2 = 170 < 180 → no collision).
        name_text, name_span = geometry.radial_arc_text(
            _CX, _CY, name_radius, company, name_fs,
            fill=fill, family=zh_family, weight=weight, max_span_deg=200.0,
        )

        # ── Bottom label path (digits/Latin — tangent textPath is fine here) ──
        defs = ""
        if bottom:
            bot_path_d = geometry.ellipse_textpath(
                _CX, _CY, bottom_radius, bottom_radius, clockwise=False
            )
            defs += f'<path id="prc-cr-bot" d="{bot_path_d}"/>'

        bottom_text = ""
        if bottom:
            bottom_text = (
                f'<text font-family="{svg.esc_attr(zh_family)}" '
                f'font-weight="{weight}" font-size="{n(bottom_fs)}" '
                f'letter-spacing="{n(bottom_spacing)}" fill="{fill}">'
                f'<textPath startOffset="50%" text-anchor="middle" '
                f'href="#prc-cr-bot">{svg.esc(bottom)}</textPath></text>'
            )

        svg_doc = (
            svg.svg_root(
                width=_VIEW_BOX[2], height=_VIEW_BOX[3], view_box_tuple=_VIEW_BOX
            )
            + f"<defs>{defs}</defs>"
            + border
            + star_el
            + name_text
            + bottom_text
            + "</svg>"
        )

        normalized = {
            "company": company,
            "bottom": bottom,
            "star": show_star,
            "color": fill,
            "weight": weight,
            "zh_font": zh_prof.family,
            "name_font_size": name_fs,
            "name_arc_span_deg": round(name_span, 2),
            "bottom_font_size": bottom_fs,
            "border_width": border_w,
            "star_radius": star_r,
        }

        # Painted bbox ≈ the outer stroke edge of the border circle, in viewBox
        # coordinates (origin-centred → shift by R+MARGIN).
        edge = _R  # stroke outer edge sits at the seal radius
        painted = (
            (_R + _MARGIN) - edge,
            (_R + _MARGIN) - edge,
            2 * edge,
            2 * edge,
        )

        return StyleResult(
            svg=svg_doc,
            normalized_params=normalized,
            warnings=warnings,
            fonts_used=fonts_used,
            view_box=_VIEW_BOX,
            painted_bbox=painted,
            canonical_size_mm=(40.0, 40.0),
            style_id="prc.company_round",
            style_version=_VERSION,
        )


STYLE = _PrcCompanyRound()

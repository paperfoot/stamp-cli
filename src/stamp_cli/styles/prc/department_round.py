"""``prc.department_round`` — PRC mainland department / special-purpose round seal.

The ~38 mm circular chop used for a company's *internal* special-purpose seals
(财务专用章 finance, 合同专用章 contract, 发票专用章 invoice, 人事专用章 HR …).
Layout, per the State Council seal regulation 国发〔1999〕25号 and the common
provincial-PSB convention for sub-42 mm department seals:

* a single circular border ring (1 mm line, ≈2.6 % of the 38 mm diameter);
* the **company name** set in 简化宋体 (Songti) curved evenly along the *top*
  arc, reading left→right (自左而右环行);
* a horizontal **purpose label** (``purpose``, e.g. ``财务专用章``) on its own
  line in the lower-centre of the field;
* an optional centred **five-pointed star** (★). Real enterprises usually carry
  one; foreign-invested ovals forbid it, but round department seals conventionally
  include it. The star is a true SVG ``<polygon>`` (NOT a glyph) so its geometry
  is exact and font-independent.

Unlike HK styles (which port STAMP4U's elliptical ``buildOvalSvg`` verbatim), the
PRC styles are *new* — but they reuse hk.oval's proven techniques: a closed-arc
``<textPath>`` for the curved name, deterministic number formatting via
:mod:`core.svg`, pinned fonts via :mod:`core.fonts`, and colors via
:mod:`core.colors`.

Coordinate space: a centred ``viewBox`` at **10 units/mm**, so the 38 mm seal is a
380-unit-diameter circle (radius 190) centred on the origin and every dimension
below reads directly in tenths of a millimetre.
"""

from __future__ import annotations

from ..base import ParamSpec, StyleMeta, StyleResult
from ...core import colors as colors_mod
from ...core import geometry, svg
from ...core.fonts import default_resolver

# Style schema version. Bump when geometry/defaults change in a way that would
# alter golden-hash output.
_VERSION = "1"

# ── Coordinate system (10 units per millimetre, centred on origin) ────────────
_UNITS_PER_MM = 10.0
_DIAMETER_MM = 38.0
_R_OUTER = _DIAMETER_MM * _UNITS_PER_MM / 2.0          # 190 — outer edge of ring
_BORDER_MM = 1.0                                        # regulation 1 mm line
_BORDER_W = _BORDER_MM * _UNITS_PER_MM                  # 10 — ring stroke width
_R_RING = _R_OUTER - _BORDER_W / 2.0                    # 185 — ring centre-line radius
_R_INNER = _R_OUTER - _BORDER_W                         # 180 — inner edge of ring

# The curved name's baseline rides a circle of this radius. On the TOP arc the
# glyph bodies extend *outward* (toward the ring) from the baseline, so this must
# clear the inner ring edge by more than the cap height. ~18 units keeps the tops
# off the 1 mm ring at the largest (40 pt) name size.
_R_TEXT = _R_INNER - 18.0                               # 162

# The viewBox is a touch larger than the seal so the 1 mm ring never clips.
_PAD = 6.0
_HALF = _R_OUTER + _PAD                                  # 196
_VIEW_BOX: tuple[float, float, float, float] = (-_HALF, -_HALF, 2 * _HALF, 2 * _HALF)

# Star geometry (centred). Provincial convention sizes the centre star at ≈33 %
# of the seal diameter on the large state-owned circle; on a small department
# seal it reads better a little smaller, so we use 30 % → outer radius ≈ 57.
_STAR_FRACTION = 0.30
_STAR_R_OUTER = _DIAMETER_MM * _UNITS_PER_MM * _STAR_FRACTION / 2.0  # 57
# A classic 5-point star's inner/outer radius ratio.
_STAR_INNER_RATIO = 0.382

# Default purpose label — finance is the most common department seal.
_DEFAULT_PURPOSE = "财务专用章"


def _name_font_size(n: int) -> int:
    """Point size for the curved company name of ``n`` CJK characters.

    The name rides the *top* arc and must stay within roughly the upper 180° so
    it never spills below the horizontal midline or kisses the 1 mm ring. The
    arc baseline circumference for the top semicircle on radius _R_TEXT (172) is
    ≈540 units, so the (size + tracking) advance per glyph must keep ``n`` glyphs
    under that. Tuned conservatively from the rendered proof, mirroring hk.oval's
    char-count step tables rather than a linear fit.
    """
    if n == 0:
        return 0
    if n <= 6:
        return 40
    if n <= 9:
        return 34
    if n <= 12:
        return 28
    if n <= 15:
        return 24
    if n <= 18:
        return 21
    return 18


def _purpose_font_size(n: int) -> int:
    """Point size for the horizontal purpose label of ``n`` CJK characters."""
    if n == 0:
        return 0
    if n <= 4:
        return 38
    if n <= 6:
        return 30
    if n <= 8:
        return 24
    return 20


def _letter_spacing(n: int) -> float:
    """Extra tracking for the curved name so short names spread along the arc.

    Kept small for longer names — the binding constraint there is *fitting* the
    top arc, not spreading it. resvg zeroes invalid negatives, so we never go
    below 0.
    """
    if n <= 4:
        return 12.0
    if n <= 6:
        return 7.0
    if n <= 9:
        return 3.0
    if n <= 12:
        return 1.5
    return 0.5


def _star_polygon_points(cx: float, cy: float, r_out: float, r_in: float) -> str:
    """Deterministic ``points`` string for a 5-point star centred at ``(cx,cy)``.

    Point 0 is the top vertex (pointing up); the 10 vertices alternate
    outer/inner going clockwise. Computed with the standard exact rational
    coordinates of a regular pentagram so output is byte-stable without floating
    trig (which would vary in trailing digits across platforms).
    """
    import math

    n = svg.num
    pts: list[str] = []
    for k in range(10):
        # -90° start (top), 36° per half-step, clockwise (negative direction in
        # SVG's y-down space means we ADD to the angle going clockwise visually).
        angle = math.radians(-90.0 + k * 36.0)
        radius = r_out if k % 2 == 0 else r_in
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        pts.append(f"{n(x)},{n(y)}")
    return " ".join(pts)


class _PrcDepartmentRound:
    META = StyleMeta(
        id="prc.department_round",
        country="prc",
        shape="circle",
        title="PRC department / special-purpose round seal",
        description=(
            "38 mm mainland round seal for a company's special-purpose chops "
            "(财务/合同/发票/人事 专用章): company name curved along the top arc in "
            "Songti, a horizontal purpose label in the lower-centre, and an "
            "optional centred five-pointed star. Red ink."
        ),
        canonical_size_mm=(38.0, 38.0),
        reference="国发〔1999〕25号 (State Council seal regulation) + provincial PSB convention",
    )

    PARAMS = [
        ParamSpec(
            name="company", type=str, default="", required=True,
            help="Company name (Chinese), curved along the top arc.",
        ),
        ParamSpec(
            name="purpose", type=str, default=_DEFAULT_PURPOSE,
            help="Horizontal purpose label in the lower centre, e.g. 财务专用章, "
                 "合同专用章, 发票专用章.",
        ),
        ParamSpec(
            name="star", type=bool, default=True,
            help="Show the centred five-pointed star (a real SVG polygon).",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, vermilion, …) or #RRGGBB. PRC seals "
                 "are red (#FF0000).",
        ),
        ParamSpec(
            name="weight", type=int, default=700,
            help="Font weight for the Chinese text (Songti). Seals read heavy.",
        ),
        ParamSpec(
            name="font", type=str, default="song",
            help="Font alias for the Chinese text (default Songti SC — the "
                 "regulation 简化宋体).",
        ),
    ]

    DEFAULTS = {
        "company": "",
        "purpose": _DEFAULT_PURPOSE,
        "star": True,
        "color": "red",
        "weight": 700,
        "font": "song",
    }

    def build_svg(self, **params) -> StyleResult:
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        warnings: list[str] = []

        company = str(p["company"]).strip()
        if not company:
            raise ValueError(
                "prc.department_round requires --company (the Chinese company name)."
            )
        purpose = str(p["purpose"]).strip()
        show_star = bool(p["star"])

        try:
            weight = int(p["weight"])
        except (TypeError, ValueError):
            raise ValueError(f"--weight must be an integer, got {p['weight']!r}")

        fill = colors_mod.parse(str(p["color"]))

        # ── Font (Songti for the regulation 简化宋体 look) ──────────────────────
        zh_prof = default_resolver.resolve(str(p["font"]))
        fonts_used = [zh_prof]
        if not zh_prof.supports_cjk:
            warnings.append(
                f"Font '{zh_prof.family}' may not cover CJK glyphs; the company "
                f"name and purpose label may not render."
            )
        zh_family = zh_prof.family

        # ── Sizes ──────────────────────────────────────────────────────────────
        name_fs = _name_font_size(len(company))
        purpose_fs = _purpose_font_size(len(purpose)) if purpose else 0
        # Glyph CENTRES ride this circle; pull in 0.7·fs so the outward half-height
        # clears the ring with margin. Scales with font size (fixes the flat-18u
        # clearance bug the verify caught).
        name_radius = _R_INNER - name_fs * 0.7

        n = svg.num

        # ── Border ring ──────────────────────────────────────────────────────
        # Single circular band, drawn as a stroked circle (deterministic; the
        # stroke is the 1 mm regulation line).
        ring = (
            f'<circle cx="0" cy="0" r="{n(_R_RING)}" fill="none" '
            f'stroke="{fill}" stroke-width="{n(_BORDER_W)}"/>'
        )

        # ── Top-arc company name — radial CJK placement (upright, feet inward) ──
        # Span capped so the name stays in the upper band and clears the lower
        # purpose label / star.
        name_group, name_span = geometry.radial_arc_text(
            0.0, 0.0, name_radius, company, name_fs,
            fill=fill, family=zh_family, weight=weight, max_span_deg=190.0,
        )

        # ── Centre star (real polygon) ─────────────────────────────────────────
        star_el = ""
        if show_star:
            pts = _star_polygon_points(
                0.0, 0.0, _STAR_R_OUTER, _STAR_R_OUTER * _STAR_INNER_RATIO
            )
            star_el = (
                f'<polygon points="{pts}" fill="{fill}" '
                f'fill-rule="nonzero"/>'
            )

        # ── Horizontal purpose label (lower centre) ────────────────────────────
        # Baseline placed below the star so the two don't collide. When a star is
        # shown the label sits in the lower third; without a star it sits a touch
        # higher (centre-low).
        purpose_el = ""
        if purpose:
            label_y = 118.0 if show_star else 95.0
            purpose_el = (
                f'<text x="0" y="{n(label_y)}" '
                f'font-family="{svg.esc_attr(zh_family)}" font-weight="{weight}" '
                f'font-size="{n(purpose_fs)}" fill="{fill}" '
                f'text-anchor="middle" letter-spacing="2">'
                f'{svg.esc(purpose)}</text>'
            )

        side = int(round(2 * _HALF))
        svg_doc = (
            svg.svg_root(width=side, height=side, view_box_tuple=_VIEW_BOX)
            + ring
            + name_group
            + star_el
            + purpose_el
            + "</svg>"
        )

        normalized = {
            "company": company,
            "purpose": purpose,
            "star": show_star,
            "color": fill,
            "weight": weight,
            "font": zh_prof.family,
            "name_font_size": name_fs,
            "name_arc_span_deg": round(name_span, 2),
            "purpose_font_size": purpose_fs,
            "diameter_mm": _DIAMETER_MM,
            "border_mm": _BORDER_MM,
            "star_outer_radius_units": _STAR_R_OUTER if show_star else 0,
        }

        # Painted bbox ≈ the outer ring circle, in viewBox coordinates.
        painted = (-_R_OUTER, -_R_OUTER, 2 * _R_OUTER, 2 * _R_OUTER)

        return StyleResult(
            svg=svg_doc,
            normalized_params=normalized,
            warnings=warnings,
            fonts_used=fonts_used,
            view_box=_VIEW_BOX,
            painted_bbox=painted,
            canonical_size_mm=(_DIAMETER_MM, _DIAMETER_MM),
            style_id="prc.department_round",
            style_version=_VERSION,
        )


STYLE = _PrcDepartmentRound()

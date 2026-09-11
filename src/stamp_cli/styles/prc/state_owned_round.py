"""``prc.state_owned_round`` — PRC mainland state-owned company round seal.

The classic mainland 公章: a single bold red ring, a five-pointed star dead
centre, the company name curved evenly around the **top** arc (simplified Song /
Songti, read left-to-right), and an optional horizontal purpose label below the
star (e.g. ``合同专用章`` / ``财务专用章``).

Regulatory basis — MOJ 国发〔1999〕25号 + the seal-spec reference in MEMORY:

* **Shape / size.** Circular, canonical **42 mm** diameter.
* **Border.** ~**1.2 mm** stroke = ``1.2/42 ≈ 2.857 %`` of the diameter.
* **Star.** A real five-pointed star centred on the seal, **14 mm** across =
  exactly **1/3 (33 %)** of the seal diameter. Rendered as an SVG ``<polygon>``
  (per the spec — not a font glyph), point-up.
* **Type face.** Simplified Song (Songti) for the Chinese, via the ``song``
  alias in :mod:`stamp_cli.core.fonts`.
* **Ink.** Pure red ``#FF0000`` (the mainland convention; STAMP4U ``red``).

Design notes (this is a NEW style — no STAMP4U builder to port, so the SVG is
constructed from first principles using the same primitives hk.oval relies on):

* We work in a **1000-unit** square viewBox so every ratio above maps to a round
  number: outer painted radius 490, border stroke ``0.02857·1000 ≈ 28.57``, star
  radius ``(14/42)/2·1000 ≈ 166.67``.
* The company name uses a ``<textPath>`` on a circle. As in hk.oval the path is
  built bottom-anchored with sweep-flag 1 (clockwise) and the text centred at
  ``startOffset=50%`` so it reads upright, left-to-right across the top.
* The star is emitted as a 10-vertex ``<polygon>`` (5 outer points + 5 inner
  valleys). Outer points sit on radius ``R``; the inner radius is the canonical
  regular-pentagram ratio so the arms have the correct slimness.
* The purpose label is centred under the star with ``dominant-baseline`` handled
  by an explicit baseline ``y`` (resvg's central-baseline support is "minimal" —
  PLAN.md §5 — so we never lean on it for placement).
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

# Square viewBox in a 1000-unit space. Centre at (500,500).
_VIEW_BOX: tuple[float, float, float, float] = (0.0, 0.0, 1000.0, 1000.0)
_CX, _CY = 500.0, 500.0
_UNITS = 1000.0

# ── Spec ratios (fractions of the 42 mm diameter) ─────────────────────────────
# Outer painted edge sits a hair inside the box so the stroke isn't clipped.
_OUTER_MARGIN_FRAC = 0.012            # 1.2% breathing room around the ring
_BORDER_FRAC = 1.2 / 42.0             # 1.2 mm border ≈ 2.857% of diameter
_STAR_DIA_FRAC = 14.0 / 42.0          # star is 1/3 of the seal diameter (33%)

# Regular-pentagram inner/outer radius ratio. For a 5-point star whose arms have
# the canonical pointiness, inner_r/outer_r = sin(18°)/sin(54°) ≈ 0.38197.
_STAR_INNER_RATIO = math.sin(math.radians(18)) / math.sin(math.radians(54))


def _star_polygon_points(cx: float, cy: float, outer_r: float) -> str:
    """Return the ``points`` attribute for a point-up 5-point star.

    10 vertices alternate outer (on ``outer_r``) and inner (on
    ``outer_r * _STAR_INNER_RATIO``). The first outer point is straight up
    (12 o'clock), i.e. angle -90°, so the star is upright.
    """
    inner_r = outer_r * _STAR_INNER_RATIO
    pts: list[str] = []
    for i in range(10):
        # 36° between successive (outer/inner) vertices; start pointing up.
        ang = math.radians(-90 + i * 36)
        r = outer_r if i % 2 == 0 else inner_r
        x = cx + r * math.cos(ang)
        y = cy + r * math.sin(ang)
        pts.append(f"{svg.num(x)},{svg.num(y)}")
    return " ".join(pts)


# ── Chinese arc font-size table ───────────────────────────────────────────────
# The company name wraps the top arc; longer names shrink. Sizes are in viewBox
# units (1000-unit space ≈ glyph fractions of the 42 mm seal). Hand-tuned so a
# typical 6–10 char 公司 name fills the upper band without grazing the border.
def _arc_font_size(n: int) -> float:
    if n <= 0:
        return 0.0
    if n <= 6:
        return 132.0
    if n <= 8:
        return 116.0
    if n <= 10:
        return 100.0
    if n <= 12:
        return 88.0
    if n <= 14:
        return 78.0
    if n <= 16:
        return 70.0
    return 62.0


class _PrcStateOwnedRound:
    META = StyleMeta(
        id="prc.state_owned_round",
        country="prc",
        shape="circle",
        title="PRC state-owned company round seal",
        description=(
            "Mainland 公章: a single bold red ring, a centred five-pointed star "
            "(1/3 of the diameter), the company name curved left-to-right around "
            "the top arc in Songti, and an optional horizontal purpose label "
            "below the star. 42 mm, 1.2 mm border, red #FF0000."
        ),
        canonical_size_mm=(42.0, 42.0),
        reference="MOJ 国发〔1999〕25号; DB11/T 918-2021 seal spec",
    )

    PARAMS = [
        ParamSpec(
            name="name", type=str, default="", required=True,
            help="Company name (Chinese), curved L-to-R around the top arc.",
        ),
        ParamSpec(
            name="label", type=str, default="",
            help="Optional horizontal purpose label under the star, e.g. "
                 "合同专用章 / 财务专用章. Empty for a plain 公章.",
        ),
        ParamSpec(
            name="star", type=bool, default=True,
            help="Show the central five-pointed star (regulation default: on).",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, blue, …) or #RRGGBB. Mainland seals "
                 "are red #FF0000.",
        ),
        ParamSpec(
            name="weight", type=int, default=700,
            help="Font weight for the Chinese text (seals read bold).",
        ),
        ParamSpec(
            name="font", type=str, default="song",
            help="Font alias for the Chinese text (default Songti — simplified "
                 "Song, the regulation face).",
        ),
    ]

    DEFAULTS = {
        "name": "",
        "label": "",
        "star": True,
        "color": "red",
        "weight": 700,
        "font": "song",
    }

    def build_svg(self, **params) -> StyleResult:  # noqa: C901 - linear builder
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        warnings: list[str] = []

        name = str(p["name"]).strip()
        if not name:
            raise ValueError(
                "prc.state_owned_round requires --name (the Chinese company name)."
            )
        label = str(p["label"]).strip()
        show_star = bool(p["star"])

        try:
            weight = int(p["weight"])
        except (TypeError, ValueError):
            raise ValueError(f"--weight must be an integer, got {p['weight']!r}")

        fill = colors_mod.parse(str(p["color"]))

        # ── Fonts ────────────────────────────────────────────────────────────
        zh_prof = default_resolver.resolve(str(p["font"]))
        fonts_used = [zh_prof]
        if not zh_prof.supports_cjk:
            warnings.append(
                f"Font '{zh_prof.family}' may not cover CJK glyphs; the Chinese "
                "name/label could render as tofu."
            )
        zh_family = zh_prof.family

        # ── Geometry (all derived from the spec ratios) ───────────────────────
        outer_r = _UNITS / 2.0 - _OUTER_MARGIN_FRAC * _UNITS   # painted outer edge
        border_w = _BORDER_FRAC * _UNITS                       # ring stroke width
        # The ring is stroked centred on a circle; its stroke spans
        # [r-border/2, r+border/2]. Pull the centreline in by half the stroke so
        # the OUTER edge of the stroke lands on outer_r (nothing clipped).
        ring_r = outer_r - border_w / 2.0
        # Inner clear radius (inside edge of the stroke) — texts stay inside it.
        inner_clear_r = ring_r - border_w / 2.0

        star_outer_r = (_STAR_DIA_FRAC * _UNITS) / 2.0         # 14 mm across

        # Name arc radius: glyph CENTRES ride this circle. Pull in by 0.7·fs so
        # the glyph's outward half-height (~0.5·fs) clears the inner border with
        # margin — clearance scales with font size (the bug the verify caught).
        name_fs = _arc_font_size(len(name))
        name_path_r = inner_clear_r - name_fs * 0.7

        n = svg.num

        # ── Outer ring (stroked circle — single bold band per regulation) ─────
        ring = (
            f'<circle cx="{n(_CX)}" cy="{n(_CY)}" r="{n(ring_r)}" '
            f'fill="none" stroke="{fill}" stroke-width="{n(border_w)}"/>'
        )

        # ── Central five-pointed star (real polygon) ──────────────────────────
        star_svg = ""
        if show_star:
            pts = _star_polygon_points(_CX, _CY, star_outer_r)
            star_svg = f'<polygon points="{pts}" fill="{fill}"/>'

        # ── Top name arc — radial CJK placement (each glyph upright, feet in) ──
        # A real 公章 keeps the name in the upper band with characters standing
        # along the radius, NOT tangent-sheared like Latin textPath. Cap the span
        # so a long name tightens in the upper ~210° rather than wrapping down to
        # the 3/9 o'clock latitude.
        name_group, name_span = geometry.radial_arc_text(
            _CX, _CY, name_path_r, name, name_fs,
            fill=fill, family=zh_family, weight=weight, max_span_deg=210.0,
        )

        # ── Purpose label (horizontal, centred below the star) ────────────────
        label_svg = ""
        label_fs = 0.0
        label_y = 0.0
        if label:
            # Size so a 3–6 char label fits comfortably between the star and the
            # lower ring; shrink for longer labels.
            ln = len(label)
            if ln <= 4:
                label_fs = 116.0
            elif ln <= 6:
                label_fs = 96.0
            elif ln <= 8:
                label_fs = 80.0
            else:
                label_fs = 68.0
            # Centre the label in the band BELOW the star, between the star's
            # lowest painted extent and the bottom inner rim — all in absolute
            # y (no radius/coordinate mixing). The two lower star arms reach
            # cy + star_outer_r·cos36°; the bottom rim is cy + inner_clear_r.
            star_low_y = _CY + star_outer_r * math.cos(math.radians(36))
            rim_low_y = _CY + inner_clear_r
            zone_lo = star_low_y + label_fs * 0.30   # clear the star
            zone_hi = rim_low_y - label_fs * 0.45    # clear the rim
            label_cy = (zone_lo + zone_hi) / 2.0
            # Convert visual centre to a text baseline y (≈ +0.34·fs below the
            # centre) rather than trusting dominant-baseline=central
            # (resvg support is "minimal" — PLAN.md §5).
            label_y = label_cy + label_fs * 0.34
            label_spacing = label_fs * 0.06
            label_svg = (
                f'<g font-weight="{weight}" '
                f'font-family="{svg.esc_attr(zh_family)}" fill="{fill}">'
                f'<text x="{n(_CX)}" y="{n(label_y)}" font-size="{n(label_fs)}" '
                f'letter-spacing="{n(label_spacing)}" text-anchor="middle">'
                f'{svg.esc(label)}</text></g>'
            )

        svg_doc = (
            svg.svg_root(width=_UNITS, height=_UNITS, view_box_tuple=_VIEW_BOX)
            + ring
            + star_svg
            + name_group
            + label_svg
            + "</svg>"
        )

        normalized = {
            "name": name,
            "label": label,
            "star": show_star,
            "color": fill,
            "weight": weight,
            "font": zh_prof.family,
            "name_font_size": name_fs,
            "name_arc_span_deg": round(name_span, 2),
            "name_path_radius": round(name_path_r, 3),
            "name_outer_extent": round(name_path_r + name_fs * 0.5, 3),
            "inner_clear_radius": round(inner_clear_r, 3),
            "ring_radius": round(ring_r, 3),
            "border_width": round(border_w, 3),
            "star_outer_radius": round(star_outer_r, 3) if show_star else 0,
            "label_font_size": label_fs if label else 0,
        }

        # Painted bbox ≈ the outer edge of the ring stroke, a centred square.
        painted = (
            _CX - outer_r, _CY - outer_r,
            2 * outer_r, 2 * outer_r,
        )

        return StyleResult(
            svg=svg_doc,
            normalized_params=normalized,
            warnings=warnings,
            fonts_used=fonts_used,
            view_box=_VIEW_BOX,
            painted_bbox=painted,
            canonical_size_mm=(42.0, 42.0),
            style_id="prc.state_owned_round",
            style_version=_VERSION,
        )


STYLE = _PrcStateOwnedRound()

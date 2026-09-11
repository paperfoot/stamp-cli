"""Round contract-use seal with an inward-spaced company arc and a star.

This is a graphic template, not a certified or registered company seal.
"""

from __future__ import annotations

import math

from ..base import ParamSpec, StyleMeta, StyleResult
from ...core import colors as colors_mod
from ...core import geometry, svg
from ...core.fonts import default_resolver

# Style schema version. Bump when geometry/defaults change in a way that would
# alter golden-hash output.
_VERSION = "3"

# Square drawing coordinates and the outer ink radius.
_VIEW_BOX: tuple[float, float, float, float] = (-10.0, -10.0, 460.0, 460.0)
_CX, _CY = 220.0, 220.0
_R_OUTER = 220.0  # outer edge of the painted disc, about the centre

_DEFAULT_PURPOSE = "合同专用章"  # contract-use seal

# Nominal arc the curved company-name *baseline* sweeps, centred at 12 o'clock.
# Each rotated glyph overhangs the baseline endpoints, so the painted span runs
# ~40° wider than this nominal value (measured). 180° nominal → ~220° painted,
# which keeps the lower circle clear for the horizontal 合同专用章 label — the
# canonical 合同专用章 layout (the generic 公章 with no bottom label uses ~250°).
_NAME_ARC_DEG = 180.0


# Continuous sizing within the available company-name and label bands.
def _chinese_arc_size(n: int) -> float:
    return min(46., max(24., 390. / max(1, n))) if n else 0.


def _label_size(n: int) -> float:
    return min(44., 200. / max(1, n)) if n else 0.


def _arc_letter_spacing(
    n: int, font_size: float, radius: float, arc_deg: float
) -> float:
    """Letter-spacing so ``n`` glyphs of ``font_size`` sweep ``arc_deg`` degrees.

    The name is centred at ``startOffset=50%``; resvg lays out each cluster along
    the path with ``advance = font_size + letter_spacing`` (dropping the spacing
    after the final cluster). To span an arc length of ``radius · arc_deg`` we
    solve ``(n-1)·(font_size+ls) + font_size = arc_len`` for ``ls``. Without this
    the name's *natural* CJK advance — wider than a fixed guess — wraps it most
    of the way round the circle instead of confining it to the top arc.
    """
    if n <= 1 or font_size <= 0:
        return 0.0
    arc_len = radius * math.radians(arc_deg)
    ls = (arc_len - n * font_size) / (n - 1)
    # Never negative (resvg zeroes invalid negatives anyway); don't blow the name
    # apart past ~1.4× the glyph.
    return max(2.0, min(ls, font_size * 1.4))


def _star_polygon(cx: float, cy: float, outer_r: float, fill: str) -> str:
    """A five-pointed star ``<polygon>`` centred at ``(cx, cy)``.

    Vertex math matches ``core.render.draw_filled_star``: the topmost point sits
    at -90° (straight up) and the inner radius is the regular-pentagram ratio
    ``outer_r · sin(18°) / sin(126°)``. Ten alternating outer/inner vertices.
    """
    inner_r = outer_r * math.sin(math.radians(18)) / math.sin(math.radians(126))
    pts: list[str] = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        r = outer_r if i % 2 == 0 else inner_r
        px = cx + r * math.cos(ang)
        py = cy + r * math.sin(ang)
        pts.append(f"{svg.num(px)},{svg.num(py)}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}"/>'


class _PrcContract:
    META = StyleMeta(
        id="prc.contract",
        country="prc",
        shape="circle",
        title="PRC contract seal (合同专用章)",
        description=(
            "Round mainland-China contract-use seal: a bold red border, the "
            "company name curved along the top arc, an optional centred "
            "five-pointed star, and a horizontal 合同专用章 label. Songti, "
            "vermilion, ~40mm."
        ),
        canonical_size_mm=(40.0, 40.0),
        reference="Round contract-use seal motif",
    )

    PARAMS = [
        ParamSpec(
            name="name", type=str, default="", required=True,
            help="Company name, curved along the top arc (e.g. "
                 "上海示例科技有限公司).",
        ),
        ParamSpec(
            name="purpose", type=str, default=_DEFAULT_PURPOSE,
            help="Horizontal centre label (default 合同专用章). E.g. another "
                 "专用章 designation.",
        ),
        ParamSpec(
            name="star", type=bool, default=True,
            help="Show the central five-pointed red star.",
        ),
        ParamSpec(
            name="star_scale", type=float, default=0.20,
            help="Star outer radius as a fraction of the seal diameter "
                 "(0.20 ≈ 8mm on a 40mm seal; state-owned seals use ~0.33).",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, vermilion, cinnabar, blue…) or "
                 "#RRGGBB. Red is #FF0000; vermilion is a softer ink.",
        ),
        ParamSpec(
            name="weight", type=int, default=700,
            help="Font weight for the curved name and the label.",
        ),
        ParamSpec(
            name="font", type=str, default="song",
            help="Font alias for all CJK text (default Songti SC).",
        ),
    ]

    DEFAULTS = {
        "name": "",
        "purpose": _DEFAULT_PURPOSE,
        "star": True,
        "star_scale": 0.20,
        "color": "red",
        "weight": 700,
        "font": "song",
    }

    def build_svg(self, **params) -> StyleResult:  # noqa: C901 - linear builder
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        warnings: list[str] = []

        name = str(p["name"]).strip()
        if not name:
            raise ValueError("prc.contract requires --name (the company name).")
        purpose = str(p["purpose"]).strip()
        show_star = bool(p["star"])

        try:
            weight = int(p["weight"])
        except (TypeError, ValueError):
            raise ValueError(f"--weight must be an integer, got {p['weight']!r}")
        try:
            star_scale = float(p["star_scale"])
        except (TypeError, ValueError):
            raise ValueError(
                f"--star-scale must be a number, got {p['star_scale']!r}"
            )
        if not 0 < star_scale < 0.5:
            raise ValueError(
                f"--star-scale must be between 0 and 0.5, got {star_scale}"
            )

        fill = colors_mod.parse(str(p["color"]))

        # ── Font ──────────────────────────────────────────────────────────────
        zh_prof = default_resolver.resolve(str(p["font"]))
        fonts_used = [zh_prof]
        if not zh_prof.supports_cjk:
            warnings.append(
                f"Font '{zh_prof.family}' may not cover the CJK seal glyphs."
            )
        zh_family = zh_prof.family

        # ── Sizes ─────────────────────────────────────────────────────────────
        name_fs = _chinese_arc_size(len(name))
        label_fs = _label_size(len(purpose)) if purpose else 0

        n = svg.num

        # ── Border band + name text-path radius ──────────────────────────────
        # Keep curved lettering clear of the inner edge of the circle.
        _BORDER_INNER = 208.0
        # Text ascenders project outward from the circular baseline. Reserve
        # a full em plus an eight-unit gap, without reducing the letter size.
        tp_r = _BORDER_INNER - name_fs - 8.0

        border = f'<circle cx="220" cy="220" r="214" fill="none" stroke="{fill}" stroke-width="12"/>'

        # A clockwise baseline places the name at the top of the circle.
        top_path_d = geometry.ellipse_textpath(
            _CX, _CY, tp_r, tp_r, clockwise=True
        )
        top_path = f'<path id="prc-contract-top" d="{top_path_d}"/>'

        # Curved company name. Letter-spacing is computed so the name sweeps a
        # fixed top arc (_NAME_ARC_DEG), centred at 12 o'clock, regardless of how
        # many characters it has — otherwise the natural CJK advance wraps it
        # most of the way round the circle.
        name_spacing = _arc_letter_spacing(
            len(name), name_fs, tp_r, _NAME_ARC_DEG
        )
        name_group = (
            f'<g font-weight="{weight}" font-family="{svg.esc_attr(zh_family)}" '
            f'font-size="{n(name_fs)}" fill="{fill}">'
            f'<text letter-spacing="{n(name_spacing)}">'
            f'<textPath startOffset="50%" text-anchor="middle" '
            f'href="#prc-contract-top">{svg.esc(name)}</textPath></text>'
            f'</g>'
        )

        # Central star (real polygon). Outer radius scales with the diameter.
        star_svg = ""
        star_outer_r = 0.0
        star_cy = _CY
        if show_star:
            star_outer_r = star_scale * (2 * _R_OUTER)
            # Lift the star slightly above centre so the horizontal label has
            # clear room below it (mirrors the round-seal Pillow prototype).
            star_cy = _CY - star_outer_r * 0.25
            star_svg = _star_polygon(_CX, star_cy, star_outer_r, fill)

        # Horizontal centre label, pushed below the star.
        label_svg = ""
        label_y = _CY
        if purpose:
            if show_star:
                # Baseline sits clear below the star's lowest point.
                label_y = star_cy + star_outer_r + label_fs * 0.9
            else:
                label_y = _CY + label_fs / 2
            label_svg = (
                f'<g font-weight="{weight}" '
                f'font-family="{svg.esc_attr(zh_family)}" fill="{fill}">'
                f'<text font-size="{n(label_fs)}" letter-spacing="{n(label_fs * 0.08)}" '
                f'text-anchor="middle" x="220" y="{n(label_y)}">'
                f'{svg.esc(purpose)}</text></g>'
            )

        svg_doc = (
            svg.svg_root(width=480, height=480, view_box_tuple=_VIEW_BOX)
            + border
            + f"<defs>{top_path}</defs>"
            + name_group + star_svg + label_svg
            + "</svg>"
        )

        normalized = {
            "name": name,
            "purpose": purpose,
            "star": show_star,
            "star_scale": star_scale,
            "color": fill,
            "weight": weight,
            "font": zh_prof.family,
            "name_font_size": name_fs,
            "name_letter_spacing": round(name_spacing, 3),
            "label_font_size": label_fs,
            "star_outer_radius": round(star_outer_r, 3) if show_star else 0,
            "label_baseline_y": round(label_y, 3) if purpose else 0,
        }

        # Painted bbox ≈ the outer disc (r=220 about the centre), in viewBox
        # coordinates: (0,0)..(440,440).
        painted = (0.0, 0.0, 440.0, 440.0)

        return StyleResult(
            svg=svg_doc,
            normalized_params=normalized,
            warnings=warnings,
            fonts_used=fonts_used,
            view_box=_VIEW_BOX,
            painted_bbox=painted,
            canonical_size_mm=(40.0, 40.0),
            style_id="prc.contract",
            style_version=_VERSION,
        )


STYLE = _PrcContract()

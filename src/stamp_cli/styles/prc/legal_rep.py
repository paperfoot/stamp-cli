"""``prc.legal_rep`` — PRC legal-representative personal seal (法定代表人专用章).

The small square name-seal a company's legal representative (法定代表人) signs
documents with. Unlike the round enterprise seals, this is a **personal-name
chop**: the representative's name in large Songti characters inside a square red
border, optionally captioned with a purpose label (``专用章`` by default) and an
optional small five-pointed star.

This is a NEW PRC style — there is no STAMP4U builder for it. The geometry is
designed here from the ``personal.name_chop`` square technique (PLAN.md §6): a
square frame, the name laid out as a 1-row or 2×2 grid of evenly-spaced
``<text>`` cells, and a smaller centered caption band. It follows the STAMP4U
square convention of a ``0 0 160 160`` viewBox so it composes with the rest of
the catalog.

Layout
------

* **Name** (1–4 CJK chars, the dominant element):
    - 1 char  → single large glyph, centred.
    - 2 chars → side by side on one row.
    - 3 chars → three across one row.
    - 4 chars → 2×2 grid, read top row then bottom row (right-to-left within a
      traditional chop is *not* forced — names print left-to-right here, which
      is what modern 法定代表人 seals do).
  Longer strings (a full name plus title) fall back to a single shrinking row.
* **Label** (optional, default ``专用章``): a smaller centred caption under the
  name. Pass ``--label ""`` for a pure name chop with no caption.
* **Star** (optional, off by default): a real 5-point SVG ``<polygon>`` centred
  above the name. Personal seals are not state seals, so no star unless asked.

Everything is red by default (``#FF0000`` STAMP4U red); Chinese uses Songti SC
(the ``song`` alias), the regulation face for PRC seals.
"""

from __future__ import annotations

import math

from ..base import ParamSpec, StyleMeta, StyleResult
from ...core import colors as colors_mod
from ...core import svg
from ...core.fonts import default_resolver
from ...core.text import fitted_block, weighted_font

# Style schema version. Bump when geometry/defaults change in a way that would
# alter golden-hash output.
_VERSION = "2"

# Square viewBox + centre, matching STAMP4U's buildSquareSvg convention.
_VIEW_BOX: tuple[float, float, float, float] = (0.0, 0.0, 160.0, 160.0)
_CX, _CY = 80.0, 80.0
_SIDE = 160.0

# Border geometry. A single square band ~1mm-equivalent thick (≈3% of the side),
# inset slightly from the edge so the stroke is fully painted inside the viewBox.
_BORDER_W = 5.0          # stroke width of the frame
_BORDER_INSET = 6.0      # gap from viewBox edge to the (centre of the) frame
_DEFAULT_LABEL = "专用章"

# Fraction of a grid cell a glyph's nominal point size fills. <1 leaves an air
# gap so neighbouring characters never touch — 0.78 reads dense-but-separated
# like a carved chop.
_GLYPH_FILL = 0.78

def _name_font_size(n_cols: int, n_rows: int, region_w: float, region_h: float) -> float:
    """Point size for each name glyph, fit to the available name region.

    The glyph must fit both a column cell (``region_w / n_cols`` wide) and a row
    cell (``region_h / n_rows`` tall). We take the smaller of the two fits so the
    grid never overflows, scaled by ``_GLYPH_FILL`` so adjacent glyphs keep an
    air gap. A single glyph is allowed to run larger (it owns the whole region).
    All-float arithmetic keeps output deterministic.
    """
    cell_w = region_w / n_cols
    cell_h = region_h / n_rows
    by_w = cell_w * _GLYPH_FILL
    by_h = cell_h * _GLYPH_FILL
    size = min(by_w, by_h)
    # A lone centred glyph can use the region generously.
    cap = 96.0 if (n_cols == 1 and n_rows == 1) else 72.0
    return max(18.0, min(size, cap))


def _star_polygon(cx: float, cy: float, r: float, fill: str) -> str:
    """A real upright 5-point star ``<polygon>`` of circumradius ``r``.

    Vertices alternate outer/inner radius (inner = r * sin18/sin54, the regular
    pentagram ratio ≈ 0.382), first point straight up, matching the PRC star.
    """
    inner = r * (math.sin(math.radians(18)) / math.sin(math.radians(54)))
    pts: list[str] = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5  # start at top, step 36°
        rad = r if i % 2 == 0 else inner
        px = cx + rad * math.cos(ang)
        py = cy + rad * math.sin(ang)
        pts.append(f"{svg.num(px)},{svg.num(py)}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}"/>'


class _PrcLegalRep:
    META = StyleMeta(
        id="prc.legal_rep",
        country="prc",
        shape="square",
        title="PRC legal-representative personal seal",
        description=(
            "Small square personal name-chop for a company's legal "
            "representative (法定代表人专用章): the representative's name in "
            "large Songti characters inside a square red border, an optional "
            "purpose label (专用章) below, and an optional 5-point star above. "
            "Red, Songti SC."
        ),
        canonical_size_mm=(22.0, 22.0),
        reference="PLAN.md §6 (PRC taxonomy); personal.name_chop square technique",
    )

    PARAMS = [
        ParamSpec(
            name="name", type=str, default="", required=True,
            help="Legal representative's name (1–4 CJK chars work best), laid "
                 "out as the dominant element of the seal.",
        ),
        ParamSpec(
            name="label", type=str, default=_DEFAULT_LABEL,
            help="Caption under the name (default 专用章). Pass an empty string "
                 "for a pure name chop with no caption.",
        ),
        ParamSpec(
            name="star", type=bool, default=False,
            help="Show a small 5-point star above the name (off by default — a "
                 "personal seal is not a state seal).",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, blue, purple, black, vermilion…) or "
                 "#RRGGBB. PRC convention is red (#FF0000).",
        ),
        ParamSpec(
            name="weight", type=int, default=700,
            help="Font weight for the name + label (bold reads as a carved "
                 "seal).",
        ),
        ParamSpec(
            name="zh_font", type=str, default="song",
            help="Font alias for the Chinese text (default Songti SC, the PRC "
                 "regulation seal face).",
        ),
    ]

    DEFAULTS = {
        "name": "",
        "label": _DEFAULT_LABEL,
        "star": False,
        "color": "red",
        "weight": 700,
        "zh_font": "song",
    }

    def build_svg(self, **params) -> StyleResult:  # noqa: C901 - linear builder
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        warnings: list[str] = []

        name = str(p["name"]).strip()
        if not name:
            raise ValueError(
                "prc.legal_rep requires --name (the legal representative's name)."
            )
        label = str(p["label"]).strip()
        show_star = bool(p["star"])

        try:
            weight = int(p["weight"])
        except (TypeError, ValueError):
            raise ValueError(f"--weight must be an integer, got {p['weight']!r}")

        fill = colors_mod.parse(str(p["color"]))

        # ── Fonts ─────────────────────────────────────────────────────────────
        zh_prof = weighted_font(default_resolver.resolve(str(p["zh_font"])), weight)
        fonts_used = [zh_prof]
        if not zh_prof.supports_cjk:
            warnings.append(
                f"Chinese font '{zh_prof.family}' may not cover CJK glyphs."
            )
        zh_family = zh_prof.family

        # ── Layout regions ────────────────────────────────────────────────────
        # Inner square the glyphs live in, inset from the frame stroke.
        frame_edge = _BORDER_INSET + _BORDER_W / 2.0  # inner edge of the stroke
        pad = 8.0                                      # breathing room inside frame
        inner_left = frame_edge + pad
        inner_right = _SIDE - frame_edge - pad
        inner_top = frame_edge + pad
        inner_bottom = _SIDE - frame_edge - pad

        # Reserve a caption band at the bottom for the label, and a strip at the
        # top for the star, when present.
        label_fs = 26.0 if label else 0.0
        label_band = (label_fs + 6.0) if label else 0.0
        star_r = 14.0 if show_star else 0.0
        star_band = (star_r * 2.0 + 6.0) if show_star else 0.0

        name_top = inner_top + star_band
        name_bottom = inner_bottom - label_band
        name_cx = (inner_left + inner_right) / 2.0
        name_w = inner_right - inner_left

        # ── Name grid geometry ────────────────────────────────────────────────
        chars = list(name)
        n = len(chars)
        if n <= 3:
            rows: list[list[str]] = [chars]
        elif n == 4:
            rows = [chars[:2], chars[2:]]
        else:
            # Long string (name + title): single shrinking row.
            rows = [chars]

        n_cols = max(len(r) for r in rows)
        n_rows = len(rows)
        name_h = name_bottom - name_top
        name_fs = _name_font_size(n_cols, n_rows, name_w, name_h)

        nm = svg.num

        # ── Frame (single square band) ────────────────────────────────────────
        fr = nm(frame_edge)
        side_len = nm(_SIDE - 2 * frame_edge)
        frame = (
            f'<rect x="{fr}" y="{fr}" width="{side_len}" height="{side_len}" '
            f'fill="none" stroke="{fill}" stroke-width="{nm(_BORDER_W)}"/>'
        )

        # ── Star (optional) ───────────────────────────────────────────────────
        star_svg = ""
        if show_star:
            star_cy = inner_top + star_r
            star_svg = _star_polygon(name_cx, star_cy, star_r, fill)

        # Centre the full visible name/caption block, not separately estimated
        # baselines. A star owns its own strip above the text when enabled.
        block_lines = [(''.join(row), [zh_prof], name_fs, name_fs * .12) for row in rows]
        if label:
            block_lines.append((label, [zh_prof], label_fs, 2.))
        name_group, sizes = fitted_block(block_lines,
                                         (inner_left, name_top, name_w, inner_bottom - name_top),
                                         gap=12, minimum=14, color=fill)
        name_fs = sizes[0]
        label_fs = sizes[-1] if label else 0.

        svg_doc = (
            svg.svg_root(width=_SIDE, height=_SIDE, view_box_tuple=_VIEW_BOX)
            + frame + star_svg + name_group
            + "</svg>"
        )

        normalized = {
            "name": name,
            "label": label,
            "star": show_star,
            "color": fill,
            "weight": weight,
            "zh_font": zh_prof.family,
            "name_font_size": name_fs,
            "name_rows": n_rows,
            "name_cols": n_cols,
            "label_font_size": label_fs,
            "star_radius": star_r,
        }

        # Painted bbox ≈ the frame's outer extent.
        outer = frame_edge - _BORDER_W / 2.0
        painted = (outer, outer, _SIDE - 2 * outer, _SIDE - 2 * outer)

        return StyleResult(
            svg=svg_doc,
            normalized_params=normalized,
            warnings=warnings,
            fonts_used=fonts_used,
            view_box=_VIEW_BOX,
            painted_bbox=painted,
            canonical_size_mm=(22.0, 22.0),
            style_id="prc.legal_rep",
            style_version=_VERSION,
        )


STYLE = _PrcLegalRep()

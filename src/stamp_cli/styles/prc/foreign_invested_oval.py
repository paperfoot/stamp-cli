"""``prc.foreign_invested_oval`` — PRC foreign-invested company oval seal.

The elliptical company chop authorised for foreign-invested / joint-venture /
WFOE entities, per the **1993 Guangdong provincial gazette** (
http://www.gd.gov.cn/zwgk/gongbao/1993/11/content/post_3356956.html ). Unlike a
mainland *round* enterprise seal it is plainer and follows three hard rules:

* **Shape / size.** A true ellipse, **横径 45 mm × 竖径 30 mm** → aspect **1.5**
  exactly (not STAMP4U's 1.353 HK oval). This is the *canonical* physical size.
* **Border.** A **single 1 mm** ring — no double border, no font-size-driven
  inner ellipse, none of the STAMP4U HK oval's decorative bands.
* **No star.** A five-pointed star is **forbidden** in this seal type (the star
  belongs to mainland *round* state/enterprise seals, never the foreign-invested
  oval). There is also no ``❋`` floret — that is a STAMP4U HK affectation.

The company name is laid out one of two regulation-sanctioned ways, chosen by
``layout``:

* ``horizontal`` (**横排**, default) — one or two centred horizontal lines,
  exactly the technique ``hk.oval`` uses for its Chinese block (``<tspan>`` rows
  on a ``dominant-baseline=central`` text element).
* ``curved`` (**环行**) — the name curls left→right along the **top arc** via a
  ``<textPath>`` ellipse (the same top-arc trick as ``hk.oval``'s English),
  leaving the optional English / secondary line on the **bottom arc**.

Geometry is *new* (PRC styles have no STAMP4U template) but built from the same
primitives the proof spike validated through resvg: an SVG ring drawn as an
even-odd ``<path>`` between two concentric ellipses, and top-CW / bottom-CCW
``<textPath>`` ellipses for curved text. We work in a **10 units = 1 mm** space
so the 45×30 mm seal is a 450×300-unit ellipse and the 1 mm border is 10 units —
keeping every dimension an exact, deterministic number.

Default ink is **red** for parity with the rest of the catalog (the gazette
permits blue/purple ink too — pass ``--color blue``). CJK is **Songti**
(简化宋体), the regulation face; an optional English line uses Times.
"""

from __future__ import annotations

from ..base import ParamSpec, StyleMeta, StyleResult
from ...core import colors as colors_mod
from ...core import svg
from ...core.fonts import default_resolver
from ...core.text import fitted_block, weighted_font
from ...core.seal_layout import arc_text

# Style schema version. Bump when geometry/defaults change in a way that would
# alter golden-hash output.
_VERSION = "2"

# ── Canonical geometry (10 units = 1 mm) ──────────────────────────────────────
# 45 mm × 30 mm seal → outer ellipse rx=225 ry=150 about a centre, with a 1 mm
# (=10 unit) viewBox margin so the stroke/edge never clips.
_MM = 10.0                       # units per millimetre
_W_MM, _H_MM = 45.0, 30.0        # canonical physical size
_BORDER_MM = 1.0                 # single ring width

_OUTER_RX = _W_MM * _MM / 2.0    # 225
_OUTER_RY = _H_MM * _MM / 2.0    # 150
_BORDER = _BORDER_MM * _MM       # 10  (ring thickness)
_INNER_RX = _OUTER_RX - _BORDER  # 215  (inside edge of the ring)
_INNER_RY = _OUTER_RY - _BORDER  # 140

_MARGIN = _BORDER                # viewBox padding around the outer ellipse
_VB_W = _W_MM * _MM + 2 * _MARGIN  # 470
_VB_H = _H_MM * _MM + 2 * _MARGIN  # 320
_VIEW_BOX: tuple[float, float, float, float] = (-_MARGIN, -_MARGIN, _VB_W, _VB_H)
_CX = _OUTER_RX                  # 225  (centre x, since min-x = -margin..)
_CY = _OUTER_RY                  # 150

# Curved-text path radii. On a 1.5-aspect oval the top/bottom arcs fall away
# steeply into the sides, so the text ellipse is pulled well *inside* the ring
# (bigger gap on the short y-axis than the long x-axis) to keep glyphs off the
# border and out of the near-vertical side walls. resvg centres a <textPath>
# string about startOffset=50% (the arc apex), so a tighter ellipse + modest
# letter-spacing keeps the whole name in a shallow upper/lower band.
_GAP_X = 34.0                    # inset from the inner ring on the long axis
_GAP_Y = 30.0                    # inset on the short axis (steep arc)
_TOP_RX = _INNER_RX - _GAP_X
_TOP_RY = _INNER_RY - _GAP_Y
_BOT_RX = _TOP_RX
_BOT_RY = _TOP_RY

_LAYOUTS = ("horizontal", "curved")


def _zh_size(n: int) -> float:
    """Point-size for a centred horizontal CJK line of ``n`` chars.

    Tuned to the 450×300-unit ellipse: short names run large, long ones shrink
    so a full ``示例創新科技(香港)有限公司`` still clears the ring with margin.
    A lookup (not a formula) keeps output deterministic and legible across the
    realistic 4–16 character range.
    """
    if n <= 0:
        return 0.0
    if n <= 4:
        return 70.0
    if n <= 6:
        return 58.0
    if n <= 8:
        return 48.0
    if n <= 10:
        return 40.0
    if n <= 12:
        return 34.0
    if n <= 14:
        return 30.0
    if n <= 16:
        return 26.0
    return 22.0


def _curved_zh_size(n: int) -> float:
    """Point-size for the name curved along the top arc (环行), by char count.

    Sizes are deliberately modest: on a 1.5-aspect oval the usable top arc is
    short, so even a 10-char name must stay small enough to keep its end glyphs
    out of the steep side walls.
    """
    if n <= 0:
        return 0.0
    if n <= 6:
        return 46.0
    if n <= 8:
        return 40.0
    if n <= 10:
        return 34.0
    if n <= 12:
        return 30.0
    if n <= 15:
        return 26.0
    if n <= 18:
        return 23.0
    return 20.0


def _en_size(n: int) -> float:
    """Point-size for an optional centred English line of ``n`` chars."""
    if n <= 0:
        return 0.0
    if n <= 18:
        return 30.0
    if n <= 26:
        return 24.0
    if n <= 34:
        return 20.0
    return 17.0


class _PrcForeignInvestedOval:
    META = StyleMeta(
        id="prc.foreign_invested_oval",
        country="prc",
        shape="oval",
        title="PRC foreign-invested company oval seal",
        description=(
            "Foreign-invested / joint-venture / WFOE oval chop: a true 45×30 mm "
            "ellipse (aspect 1.5) with a single 1 mm border and NO star (the "
            "star is forbidden for this seal type). Company name laid out "
            "horizontally (横排) or curved along the top arc (环行). Songti, "
            "plainer than the STAMP4U HK oval."
        ),
        canonical_size_mm=(_W_MM, _H_MM),
        reference="Guangdong provincial gazette 1993 (foreign-invested oval, 45×30mm, 1mm border, no star)",
    )

    PARAMS = [
        ParamSpec(
            name="name", type=str, default="", required=True,
            help="Company name (Chinese), e.g. 上海示例科技有限公司. The primary "
                 "line — horizontal or curved depending on --layout.",
        ),
        ParamSpec(
            name="name_line2", type=str, default="",
            help="Optional second horizontal line (横排 only), e.g. (香港)有限公司. "
                 "Manual split — not auto-derived. Ignored in curved layout.",
        ),
        ParamSpec(
            name="en", type=str, default="",
            help="Optional English line. Centred below the name in 横排; curved "
                 "along the bottom arc in 环行.",
        ),
        ParamSpec(
            name="layout", type=str, default="horizontal", enum=list(_LAYOUTS),
            help="Name arrangement: 'horizontal' (横排, centred lines) or "
                 "'curved' (环行, along the top arc). Both are gazette-sanctioned.",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, blue, purple, black, vermilion…) or "
                 "#RRGGBB. Gazette permits blue/purple for this seal too.",
        ),
        ParamSpec(
            name="weight", type=int, default=700,
            help="Font weight for the CJK + English text.",
        ),
        ParamSpec(
            name="zh_font", type=str, default="song",
            help="Font alias for the Chinese text (default Songti, 简化宋体).",
        ),
        ParamSpec(
            name="en_font", type=str, default="times",
            help="Font alias for the optional English line (default Times).",
        ),
    ]

    DEFAULTS = {
        "name": "",
        "name_line2": "",
        "en": "",
        "layout": "horizontal",
        "color": "red",
        "weight": 700,
        "zh_font": "song",
        "en_font": "times",
    }

    def build_svg(self, **params) -> StyleResult:  # noqa: C901 - linear builder
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        warnings: list[str] = []

        name = str(p["name"]).strip()
        if not name:
            raise ValueError(
                "prc.foreign_invested_oval requires --name (the company name)."
            )
        name2 = str(p["name_line2"]).strip()
        english = str(p["en"]).strip()

        layout = str(p["layout"]).strip().lower()
        if layout not in _LAYOUTS:
            raise ValueError(
                f"--layout must be one of {', '.join(_LAYOUTS)}; got {layout!r}."
            )

        try:
            weight = int(p["weight"])
        except (TypeError, ValueError):
            raise ValueError(f"--weight must be an integer, got {p['weight']!r}")

        fill = colors_mod.parse(str(p["color"]))

        # ── Fonts ────────────────────────────────────────────────────────────
        zh_prof = weighted_font(default_resolver.resolve(str(p["zh_font"])), weight)
        fonts_used = [zh_prof]
        en_prof = None
        if english:
            en_prof = weighted_font(default_resolver.resolve(str(p["en_font"])), weight)
            fonts_used.append(en_prof)
        if not zh_prof.supports_cjk:
            warnings.append(
                f"Chinese font '{zh_prof.family}' may not cover CJK glyphs."
            )
        if layout == "curved" and name2:
            warnings.append(
                "name_line2 is ignored in curved layout; fold it into --name."
            )

        zh_family = zh_prof.family
        en_family = en_prof.family if en_prof else ""

        n = svg.num

        # ── The single 1 mm border ring (even-odd between two ellipses) ───────
        # Outer ellipse minus the inner ellipse → a clean ring of width _BORDER.
        ring = (
            f'<path fill="{fill}" fill-rule="evenodd" '
            f'd="M {n(_CX)},{n(_CY)} '
            f'm -{n(_OUTER_RX)},0 '
            f'a {n(_OUTER_RX)},{n(_OUTER_RY)} 0 1,0 {n(2 * _OUTER_RX)},0 '
            f'a {n(_OUTER_RX)},{n(_OUTER_RY)} 0 1,0 -{n(2 * _OUTER_RX)},0 z '
            f'M {n(_CX)},{n(_CY)} '
            f'm -{n(_INNER_RX)},0 '
            f'a {n(_INNER_RX)},{n(_INNER_RY)} 0 1,0 {n(2 * _INNER_RX)},0 '
            f'a {n(_INNER_RX)},{n(_INNER_RY)} 0 1,0 -{n(2 * _INNER_RX)},0 z"/>'
        )

        # Curved (环行) arc-length placement skews and can clip long CJK names on
        # the steep side walls of a 1.5-aspect ellipse (verify flagged this). Cap
        # it: past 8 characters, fall back to the always-clean, equally
        # gazette-sanctioned horizontal layout with a warning.
        if layout == "curved" and len(name) > 8:
            layout = "horizontal"
            warnings.append(
                "curved layout falls back to horizontal for names longer than 8 "
                "characters (avoids skew/clipping on the ellipse side walls); pass "
                "--layout horizontal to silence, or shorten the curved name."
            )

        defs_paths = ""
        body = ""

        if layout == "curved":
            # Both runs use the same visible-ink ellipse, rather than giving
            # top and bottom text the same baseline and unequal border gaps.
            body, zh1_fs_out = arc_text(
                name, [zh_prof], _CX, _CY, _TOP_RX, _TOP_RY,
                ink=fill, size=_curved_zh_size(len(name)), key='fio-top',
                spacing=2, band_width=62, sweep=176)
            zh2_fs_out = en_fs_out = 0.
            if english:
                bottom, en_fs_out = arc_text(
                    english, [en_prof], _CX, _CY, _BOT_RX, _BOT_RY,
                    ink=fill, size=_en_size(len(english)), key='fio-bot',
                    bottom=True, spacing=1.5, band_width=62, sweep=176)
                body += bottom

        else:
            # ── 横排: one/two centred horizontal CJK lines + optional English. ─
            two = bool(name2)
            zh1_fs = _zh_size(len(name))
            zh2_fs = _zh_size(len(name2)) if two else 0.0
            en_fs = _en_size(len(english)) if english else 0.0

            # Fit the complete bilingual block to a rectangle safely inside
            # the ellipse. Visible ink, rather than nominal baselines, is centred.
            block_lines = [(name, [zh_prof], zh1_fs, 1.5)]
            if two:
                block_lines.append((name2, [zh_prof], zh2_fs, 1.5))
            if english:
                block_lines.append((english, [en_prof], en_fs, .8))
            body, sizes = fitted_block(block_lines,
                                       (_CX - 176, _CY - 82, 352, 164),
                                       gap=14, minimum=14, color=fill,
                                       ellipse=(_CX, _CY, _INNER_RX - 10, _INNER_RY - 10))
            zh1_fs_out = sizes[0]
            zh2_fs_out = sizes[1] if two else 0.
            en_fs_out = sizes[-1] if english else 0.

        svg_doc = (
            svg.svg_root(width=_VB_W, height=_VB_H, view_box_tuple=_VIEW_BOX)
            + ring
            + (f"<defs>{defs_paths}</defs>" if defs_paths else "")
            + body
            + "</svg>"
        )

        normalized = {
            "name": name,
            "name_line2": name2 if layout == "horizontal" else "",
            "en": english,
            "layout": layout,
            "color": fill,
            "weight": weight,
            "zh_font": zh_prof.family,
            "en_font": en_prof.family if en_prof else "",
            "name_font_size": zh1_fs_out,
            "name_line2_font_size": zh2_fs_out,
            "en_font_size": en_fs_out,
        }

        # Painted bbox ≈ the outer ellipse: (0,0)..(2*rx, 2*ry) in viewBox coords.
        painted = (0.0, 0.0, 2 * _OUTER_RX, 2 * _OUTER_RY)

        return StyleResult(
            svg=svg_doc,
            normalized_params=normalized,
            warnings=warnings,
            fonts_used=fonts_used,
            view_box=_VIEW_BOX,
            painted_bbox=painted,
            canonical_size_mm=(_W_MM, _H_MM),
            style_id="prc.foreign_invested_oval",
            style_version=_VERSION,
        )


STYLE = _PrcForeignInvestedOval()

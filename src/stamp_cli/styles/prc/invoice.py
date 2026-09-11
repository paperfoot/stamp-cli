"""``prc.invoice`` — mainland PRC 发票专用章 (invoice special seal).

The oval seal a Chinese enterprise stamps on the invoices (发票) it issues. It is
legally distinct from the company seal (公章) and from the foreign-invested oval:
it always carries the literal label **发票专用章** and, by long-standing tax
practice, the issuer's **tax registration number** (税号 / 纳税人识别号).

Layout (top → bottom), all inside a single thin elliptical border:

  * **Company name** curved evenly along the top arc (环行, left→right).
  * A small red **five-pointed star** at top dead-centre, just under the name.
  * The **发票专用章** label as one centred horizontal line through the middle.
  * The **tax registration number** as a straight centred line below the label.

This is *plainer* than :mod:`stamp_cli.styles.hk.oval`: a single border (not a
double band + font-driven inner ellipse) and no bottom floret. It reuses
hk.oval's proven techniques — ellipse ring as a two-subpath ``<path>`` and a
``<textPath>`` on a defined ellipse for the curved top name — so it rasterises
identically through resvg.

Design notes / fidelity:

  * **Shape.** Oval, canonical **40 × 30 mm** (aspect 4:3, the common 发票专用章
    size). viewBox mirrors hk.oval's ``-15 -15 490 370`` so px-width scaling and
    the centre ``(230,170)`` are shared.
  * **Star.** A real 5-point SVG ``<polygon>`` (NOT the ``❋`` floret),点 up,
    circum-radius ≈ 18 user-units (~3 mm on the canonical seal), sitting just
    below the curved name. PRC seal stars are simple solid pentagrams.
  * **Color.** Mainland seals are red — default ``#FF0000`` (STAMP4U ``red``).
  * **Font.** Songti SC (``song`` alias) for all CJK + the digits of the tax
    number, matching the regulation's 简化宋体 requirement. No Symbols font is
    needed because the star is drawn, not glyph-shaped.

The tax number is a free string (``tax_no``) — formatted deterministically by
stripping surrounding whitespace only; the canonical 统一社会信用代码 is 18 chars
but older 15-char 税务登记证号 are still seen on legacy seals, so we don't reformat.
"""

from __future__ import annotations

import math

from ..base import ParamSpec, StyleMeta, StyleResult
from ...core import colors as colors_mod
from ...core import svg
from ...core.fonts import default_resolver

# Style schema version. Bump when geometry/defaults change in a way that would
# alter golden-hash output.
_VERSION = "1"

# viewBox + centre shared with hk.oval (aspect 490/370). The *painted* oval is
# narrower than hk.oval (4:3, not ~1.35:1) but the canvas is identical so
# px-width / dpi scaling behaves the same across PRC + HK ovals.
_VIEW_BOX: tuple[float, float, float, float] = (-15.0, -15.0, 490.0, 370.0)
_CX, _CY = 230.0, 170.0

# Outer painted ellipse radii (user units). 4:3 oval centred in the canvas.
# rx 215 / ry 161 ≈ 40 mm × 30 mm at the same scale hk.oval uses for 45×30.
_RX_OUT = 215.0
_RY_OUT = 161.0
_BORDER = 6.0  # ~1 mm border at the canonical size (plain single ring)


# ── Size tables (char-count driven, mirroring hk.oval's approach) ─────────────
def _name_size(n: int) -> tuple[int, float]:
    """``(font_size, letter_spacing)`` for the curved top company name.

    Tuned for the top arc of the 40 mm oval: shorter names sit larger, long
    names step down so they still fit one revolution of the arc.
    """
    if n == 0:
        return 0, 0.0
    if n <= 6:
        return 34, 1.0
    if n <= 9:
        return 28, 1.0
    if n <= 12:
        return 24, 0.5
    if n <= 16:
        return 21, 0.0
    if n <= 20:
        return 18, 0.0
    if n <= 26:
        return 16, -0.5
    return 14, -1.0


def _label_size(n: int) -> int:
    """Point-size for the centred 发票专用章 label (n is its char count)."""
    if n == 0:
        return 0
    if n <= 4:
        return 46
    if n <= 5:
        return 40
    if n <= 6:
        return 34
    return 28


class _PrcInvoice:
    META = StyleMeta(
        id="prc.invoice",
        country="prc",
        shape="oval",
        title="PRC invoice special seal (发票专用章)",
        description=(
            "Mainland oval invoice seal: company name curved along the top arc, "
            "a centred five-pointed star, the 发票专用章 label across the middle, "
            "and the tax registration number on a line below. Single thin border, "
            "red ink, Songti. Distinct from the foreign-invested oval and the "
            "company seal."
        ),
        canonical_size_mm=(40.0, 30.0),
        reference="PRC 国发〔1999〕25号 + tax-practice 发票专用章 convention",
    )

    PARAMS = [
        ParamSpec(
            name="company", type=str, default="", required=True,
            help="Company name (中文), curved along the top arc, e.g. "
                 "上海示例科技有限公司.",
        ),
        ParamSpec(
            name="tax_no", type=str, default="",
            help="Tax registration number / 统一社会信用代码 (18 chars) shown on "
                 "the line below the label. Optional.",
        ),
        ParamSpec(
            name="label", type=str, default="发票专用章",
            help="Centred label across the middle (default 发票专用章).",
        ),
        ParamSpec(
            name="star", type=bool, default=True,
            help="Show the central five-pointed star.",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, blue, purple, black, vermilion…) or "
                 "#RRGGBB. Mainland seals are red (#FF0000).",
        ),
        ParamSpec(
            name="weight", type=int, default=700,
            help="Font weight for all text (seals read bold).",
        ),
        ParamSpec(
            name="zh_font", type=str, default="song",
            help="Font alias for the Chinese text + digits (default Songti SC, "
                 "the regulation's 简化宋体).",
        ),
    ]

    DEFAULTS = {
        "company": "",
        "tax_no": "",
        "label": "发票专用章",
        "star": True,
        "color": "red",
        "weight": 700,
        "zh_font": "song",
    }

    def build_svg(self, **params) -> StyleResult:  # noqa: C901 - linear builder
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        warnings: list[str] = []

        company = str(p["company"]).strip()
        if not company:
            raise ValueError("prc.invoice requires --company (the Chinese company name).")
        tax_no = str(p["tax_no"]).strip()
        label = str(p["label"]).strip()
        show_star = bool(p["star"])

        try:
            weight = int(p["weight"])
        except (TypeError, ValueError):
            raise ValueError(f"--weight must be an integer, got {p['weight']!r}")

        fill = colors_mod.parse(str(p["color"]))

        # ── Fonts ────────────────────────────────────────────────────────────
        # Songti SC for every glyph (CJK + Latin digits in the tax number). The
        # star is a drawn polygon, so no Symbols/dingbat font is required.
        zh_prof = default_resolver.resolve(str(p["zh_font"]))
        fonts_used = [zh_prof]
        if not zh_prof.supports_cjk:
            warnings.append(
                f"Chinese font '{zh_prof.family}' may not cover CJK glyphs."
            )
        zh_family = zh_prof.family

        # ── Sizes ──────────────────────────────────────────────────────────────
        name_fs, name_spacing = _name_size(len(company))
        label_fs = _label_size(len(label)) if label else 0
        # Tax number: a straight digit line; size by length so 18 chars fit the
        # oval's width comfortably.
        if tax_no:
            tax_fs = 30 if len(tax_no) <= 12 else (24 if len(tax_no) <= 16 else 20)
        else:
            tax_fs = 0

        # ── Geometry ─────────────────────────────────────────────────────────
        # Single border ring (two-subpath even-odd path, like hk.oval's bands).
        rx_in = _RX_OUT - _BORDER
        ry_in = _RY_OUT - _BORDER
        # Top text-path ellipse: inside the border so the curved name hugs the
        # top arc. The baseline sits a full glyph-height in from the ring (text
        # grows *outward* from the baseline toward the border) so even the end
        # characters at the sides clear the border line.
        tp_rx = rx_in - 4 - name_fs
        tp_ry = ry_in - 4 - name_fs

        n = svg.num

        # Outer single ring: outer ellipse CW then inner ellipse CCW (even-odd
        # fill leaves a band of width _BORDER).
        ring = (
            f'<path fill="{fill}" fill-rule="evenodd" '
            f'd="M {n(_CX)},{n(_CY)} m -{n(_RX_OUT)},0 '
            f'a {n(_RX_OUT)},{n(_RY_OUT)} 0 1,0 {n(2 * _RX_OUT)},0 '
            f'a {n(_RX_OUT)},{n(_RY_OUT)} 0 1,0 -{n(2 * _RX_OUT)},0 z '
            f'M {n(_CX)},{n(_CY)} m -{n(rx_in)},0 '
            f'a {n(rx_in)},{n(ry_in)} 0 1,0 {n(2 * rx_in)},0 '
            f'a {n(rx_in)},{n(ry_in)} 0 1,0 -{n(2 * rx_in)},0 z"/>'
        )

        # TOP text path (same construction as hk.oval): starts at the bottom of
        # the ellipse, sweep flag 1 (CW) so the name centres along the top arc.
        top_path = (
            f'<path id="prc-inv-top" d="M {n(_CX)},{n(_CY + tp_ry)} '
            f'a {n(tp_rx)},{n(tp_ry)} 0 0,1 -{n(tp_rx)},-{n(tp_ry)} '
            f'a {n(tp_rx)},{n(tp_ry)} 0 0,1 {n(tp_rx)},-{n(tp_ry)} '
            f'a {n(tp_rx)},{n(tp_ry)} 0 0,1 {n(tp_rx)},{n(tp_ry)} '
            f'a {n(tp_rx)},{n(tp_ry)} 0 0,1 -{n(tp_rx)},{n(tp_ry)} z"/>'
        )

        # Curved company name along the top arc.
        name_group = (
            f'<g font-weight="{weight}" font-family="{svg.esc_attr(zh_family)}" '
            f'font-size="{n(name_fs)}" fill="{fill}">'
            f'<text letter-spacing="{n(name_spacing)}">'
            f'<textPath startOffset="50%" text-anchor="middle" '
            f'href="#prc-inv-top">{svg.esc(company)}</textPath></text>'
            f'</g>'
        )

        # ── Central five-pointed star (real polygon, point up) ─────────────────
        # Circum-radius in user units (~3 mm on the canonical seal). Sits just
        # below the curved name, above the label.
        star_r = 18.0
        star_cy = _CY - 52.0  # upper third, clear of the curved name and label
        star_svg = ""
        if show_star:
            star_svg = (
                f'<polygon fill="{fill}" '
                f'points="{_star_points(_CX, star_cy, star_r)}"/>'
            )

        # ── Centred label (发票专用章) — one horizontal line through the middle ──
        label_svg = ""
        if label:
            # Baseline a touch below centre; dominant-baseline central keeps it
            # vertically centred on that line (resvg supports it for plain text).
            label_y = _CY + 22.0
            label_svg = (
                f'<text font-weight="{weight}" '
                f'font-family="{svg.esc_attr(zh_family)}" '
                f'font-size="{n(label_fs)}" fill="{fill}" '
                f'x="{n(_CX)}" y="{n(label_y)}" text-anchor="middle" '
                f'dominant-baseline="central" letter-spacing="4">'
                f'{svg.esc(label)}</text>'
            )

        # ── Tax registration number — straight centred line below the label ────
        tax_svg = ""
        if tax_no:
            tax_y = _CY + 96.0
            tax_svg = (
                f'<text font-weight="{weight}" '
                f'font-family="{svg.esc_attr(zh_family)}" '
                f'font-size="{n(tax_fs)}" fill="{fill}" '
                f'x="{n(_CX)}" y="{n(tax_y)}" text-anchor="middle" '
                f'dominant-baseline="central" letter-spacing="1">'
                f'{svg.esc(tax_no)}</text>'
            )

        svg_doc = (
            svg.svg_root(width=490, height=370, view_box_tuple=_VIEW_BOX)
            + ring
            + f"<defs>{top_path}</defs>"
            + name_group + star_svg + label_svg + tax_svg
            + "</svg>"
        )

        normalized = {
            "company": company,
            "tax_no": tax_no,
            "label": label,
            "star": show_star,
            "color": fill,
            "weight": weight,
            "zh_font": zh_prof.family,
            "company_font_size": name_fs,
            "company_letter_spacing": name_spacing,
            "label_font_size": label_fs,
            "tax_no_font_size": tax_fs,
            "star_radius": star_r if show_star else 0,
        }

        # Painted bbox = the outer ellipse in viewBox coordinates.
        painted = (
            _CX - _RX_OUT, _CY - _RY_OUT,
            2 * _RX_OUT, 2 * _RY_OUT,
        )

        return StyleResult(
            svg=svg_doc,
            normalized_params=normalized,
            warnings=warnings,
            fonts_used=fonts_used,
            view_box=_VIEW_BOX,
            painted_bbox=painted,
            canonical_size_mm=(40.0, 30.0),
            style_id="prc.invoice",
            style_version=_VERSION,
        )


def _star_points(cx: float, cy: float, r: float) -> str:
    """Five-pointed star polygon points (point up), as a deterministic string.

    Outer vertices at radius ``r`` starting at the top (−90°), inner vertices at
    ``r * sin(18°)/sin(54°)`` (the regular pentagram ratio ≈ 0.382), interleaved.
    Coordinates are formatted with :func:`svg.num` so output is byte-stable.
    """
    inner = r * math.sin(math.radians(18)) / math.sin(math.radians(54))
    pts: list[str] = []
    for k in range(5):
        # Outer point.
        ao = math.radians(-90 + 72 * k)
        ox = cx + r * math.cos(ao)
        oy = cy + r * math.sin(ao)
        pts.append(f"{svg.num(ox)},{svg.num(oy)}")
        # Inner point (halfway to the next outer point).
        ai = math.radians(-90 + 72 * k + 36)
        ix = cx + inner * math.cos(ai)
        iy = cy + inner * math.sin(ai)
        pts.append(f"{svg.num(ix)},{svg.num(iy)}")
    return " ".join(pts)


STYLE = _PrcInvoice()

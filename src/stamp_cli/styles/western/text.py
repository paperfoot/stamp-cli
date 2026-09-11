"""``western.text`` — generic Western rectangular text stamp.

The plain office stamp used everywhere outside the CJK world: a rounded
rectangle (single or double border) with one or more centered text lines, the
first line set largest. Think ``PAID``, ``APPROVED``, ``RECEIVED 2026-05-29``,
``CERTIFIED TRUE COPY``.

It reuses the rectangle technique STAMP4U's ``buildRectangleSvg`` established —
a fixed viewBox, a stroked border path, and centered ``<text>`` lines with
``dominant-baseline="central"`` — but generalizes it to an arbitrary number of
lines and drops the HK "For and on behalf of" signature line (a stamp like this
never has one). The result is still SVG-first and rasterizes through the same
pinned-font ``resvg`` path as every other style.

Two ways to supply content, both deterministic:

* ``lines`` — the text, in order, first line largest. Accepts a JSON array
  (``["PAID","2026-05-29"]`` via ``generate --params``) **or** a single string
  on the nested CLI, split on newlines or ``|`` (``--lines "PAID|2026-05-29"``).
* ``preset`` — ``PAID`` / ``APPROVED`` / ``CERTIFIED TRUE COPY``. Supplies the
  canonical wording when ``lines`` is empty; ignored once ``lines`` is given.

Fonts: a Latin face by default (``times``). A CJK fallback (``zh_font``, Songti)
is pinned alongside it so a company name in Chinese still shapes correctly via
resvg glyph fallback under ``skip_system_fonts=True`` — the same trick
``hk.oval`` uses to pull ``❋`` from Noto Sans Symbols 2.
"""

from __future__ import annotations

from ..base import ParamSpec, StyleMeta, StyleResult
from ...core import colors as colors_mod
from ...core import svg
from ...core.fonts import default_resolver

# Style schema version. Bump when geometry/defaults change in a way that would
# alter golden-hash output.
_VERSION = "1"

# Fixed canvas. 360×200 (aspect 1.8) is a comfortable office-stamp rectangle;
# physical size ~38×21 mm at the canonical scale below.
_VIEW_BOX: tuple[float, float, float, float] = (0.0, 0.0, 360.0, 200.0)
_W, _H = 360.0, 200.0
_CX = _W / 2.0

# Canonical preset wordings. Keys are the enum values (upper-case, as stamped).
_PRESETS: dict[str, list[str]] = {
    "PAID": ["PAID"],
    "APPROVED": ["APPROVED"],
    "CERTIFIED TRUE COPY": ["CERTIFIED", "TRUE COPY"],
}
_PRESET_NONE = "none"


def _split_lines(value: object) -> list[str]:
    """Normalize the ``lines`` param into a clean list of non-empty strings.

    Accepts a list (JSON array via ``generate --params``) or a string (nested
    CLI), splitting a string on newlines or ``|`` so a single ``--lines`` option
    can carry several lines. Whitespace is trimmed; empty lines are dropped.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = [str(v) for v in value]
    else:
        # A single string from the CLI: split on newline or pipe. Guard against
        # an empty-list default that Click stringified to "[]" before reaching us.
        s = str(value).strip()
        if s in ("", "[]", "None"):
            return []
        items = s.replace("|", "\n").split("\n")
    return [ln.strip() for ln in items if ln.strip()]


def _line_font_size(text: str, *, first: bool) -> int:
    """Point size for one line: largest for the first line, smaller below.

    Sizes step down by the line's character count so long lines stay within the
    band. Values are integers → deterministic SVG bytes.
    """
    n = len(text)
    if first:
        if n <= 7:
            return 64
        if n <= 10:
            return 52
        if n <= 14:
            return 42
        if n <= 20:
            return 32
        if n <= 28:
            return 24
        return 20
    # Subsequent lines: a notch smaller than a first line of the same length.
    if n <= 7:
        return 40
    if n <= 12:
        return 30
    if n <= 20:
        return 24
    if n <= 30:
        return 19
    return 16


def _is_wide(ch: str) -> bool:
    """True for full-width glyphs (CJK, fullwidth forms) that advance ~1em.

    Covers the CJK ideograph blocks, CJK punctuation / fullwidth range, and
    Hiragana/Katakana — everything that, unlike Latin, takes a whole em of width
    and so must shrink the per-line size estimate accordingly.
    """
    o = ord(ch)
    return (
        0x1100 <= o <= 0x115F        # Hangul Jamo
        or 0x2E80 <= o <= 0xA4CF     # CJK radicals … Yi (incl. ideographs, kana)
        or 0xAC00 <= o <= 0xD7A3     # Hangul syllables
        or 0xF900 <= o <= 0xFAFF     # CJK compat ideographs
        or 0xFE30 <= o <= 0xFE4F     # CJK compat forms
        or 0xFF00 <= o <= 0xFF60     # fullwidth forms
        or 0xFFE0 <= o <= 0xFFE6     # fullwidth signs
    )


def _est_width(text: str, size: float) -> float:
    """Estimate the rendered advance width of ``text`` at ``size`` (px units).

    Full-width glyphs count ~1.0em; Latin/ASCII in a bold serif averages ~0.64em
    (measured against Times Bold — 0.58 under-estimated and let long lines clip).
    Plus the 0.5px letter-spacing applied between clusters.
    """
    if not text:
        return 0.0
    width = sum((1.0 if _is_wide(ch) else 0.64) * size for ch in text)
    width += 0.5 * (len(text) - 1)  # letter-spacing between clusters
    return width


def _fit_width(text: str, size: int, usable_w: float) -> int:
    """Largest size ≤ ``size`` whose estimated width fits ``usable_w``.

    Shrinks down to a floor of 10, then — so an over-long line can never clip —
    drops below the floor if even size 10 overflows (a very long single line just
    gets small rather than running off both edges).
    """
    s = size
    while s > 10 and _est_width(text, s) > usable_w:
        s -= 1
    while s > 4 and _est_width(text, s) > usable_w:
        s -= 1  # hard overflow guard below the soft floor
    return s


class _WesternText:
    META = StyleMeta(
        id="western.text",
        country="western",
        shape="rectangle",
        title="Western rectangular text stamp",
        description=(
            "Generic Western office stamp: a rounded rectangle (single or double "
            "border) with one or more centered text lines, first line largest. "
            "Presets: PAID, APPROVED, CERTIFIED TRUE COPY. No signature line. "
            "Reuses the hk.rect rectangle/centered-text technique."
        ),
        canonical_size_mm=(38.0, 21.0),
        reference="STAMP4U buildRectangleSvg (generalized; signature line removed)",
    )

    PARAMS = [
        ParamSpec(
            name="lines", type=list, default=None,
            help="Text lines, in order, first line largest. JSON array "
                 "(['PAID','2026-05-29']) or a single string split on newline "
                 "or '|' on the CLI (--lines 'PAID|2026-05-29'). Repeatable.",
        ),
        ParamSpec(
            name="preset", type=str, default=_PRESET_NONE,
            enum=[_PRESET_NONE, "PAID", "APPROVED", "CERTIFIED TRUE COPY"],
            help="Canonical wording used when --lines is empty: PAID, APPROVED, "
                 "or CERTIFIED TRUE COPY. Ignored once --lines is given.",
        ),
        ParamSpec(
            name="double_border", type=bool, default=False,
            help="Draw a second, inner border line (double border) instead of a "
                 "single border.",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, blue, purple, black, vermilion…) or "
                 "#RRGGBB. Default red.",
        ),
        ParamSpec(
            name="weight", type=int, default=700,
            help="Font weight for the text (bold by default).",
        ),
        ParamSpec(
            name="font", type=str, default="times",
            help="Latin font alias for the text (default Times New Roman). Also "
                 "try arial, helvetica, or an absolute .ttf/.ttc path.",
        ),
        ParamSpec(
            name="zh_font", type=str, default="song",
            help="CJK fallback font pinned alongside the Latin face so a Chinese "
                 "company name still renders (default Songti SC).",
        ),
    ]

    DEFAULTS = {
        "lines": [],
        "preset": _PRESET_NONE,
        "double_border": False,
        "color": "red",
        "weight": 700,
        "font": "times",
        "zh_font": "song",
    }

    def build_svg(self, **params) -> StyleResult:
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        warnings: list[str] = []

        lines = _split_lines(p["lines"])
        preset = str(p["preset"]).strip()
        if not lines and preset and preset != _PRESET_NONE:
            if preset not in _PRESETS:
                raise ValueError(
                    f"unknown preset {preset!r}. Choose one of: "
                    f"{', '.join(_PRESETS)}."
                )
            lines = list(_PRESETS[preset])
        if not lines:
            raise ValueError(
                "western.text requires --lines (or a --preset of "
                f"{', '.join(_PRESETS)})."
            )

        double_border = bool(p["double_border"])

        try:
            weight = int(p["weight"])
        except (TypeError, ValueError):
            raise ValueError(f"--weight must be an integer, got {p['weight']!r}")

        fill = colors_mod.parse(str(p["color"]))

        # ── Fonts ────────────────────────────────────────────────────────────
        # Latin face is the primary family; the CJK face is pinned as a fallback
        # so Chinese glyphs shape under skip_system_fonts (resvg falls back across
        # every file in font_files). Mirrors hk.oval's Symbols + Symbols2 pin.
        latin_prof = default_resolver.resolve(str(p["font"]))
        zh_prof = default_resolver.resolve(str(p["zh_font"]))
        fonts_used = [latin_prof, zh_prof]
        latin_family = latin_prof.family

        has_cjk = any(any(ord(ch) > 0x2E7F for ch in ln) for ln in lines)
        if has_cjk and not zh_prof.supports_cjk:
            warnings.append(
                f"CJK text present but fallback font '{zh_prof.family}' may not "
                "cover CJK glyphs."
            )

        n = svg.num

        # ── Border(s) ─────────────────────────────────────────────────────────
        # A rounded outer rectangle outline (stroked, no fill), and optionally a
        # second inner outline 6 units in. Stroke widths scale with the canvas.
        sw_outer = 5.0
        rx_outer = 16.0
        inset = 4.0  # outer rect inset from the viewBox edge
        ox, oy = inset, inset
        ow, oh = _W - 2 * inset, _H - 2 * inset
        border = (
            f'<rect x="{n(ox)}" y="{n(oy)}" width="{n(ow)}" height="{n(oh)}" '
            f'rx="{n(rx_outer)}" ry="{n(rx_outer)}" fill="none" '
            f'stroke="{fill}" stroke-width="{n(sw_outer)}"/>'
        )
        if double_border:
            gap = 7.0
            ix, iy = ox + gap, oy + gap
            iw, ih = ow - 2 * gap, oh - 2 * gap
            rx_inner = max(rx_outer - gap, 2.0)
            border += (
                f'<rect x="{n(ix)}" y="{n(iy)}" width="{n(iw)}" height="{n(ih)}" '
                f'rx="{n(rx_inner)}" ry="{n(rx_inner)}" fill="none" '
                f'stroke="{fill}" stroke-width="{n(3.0)}"/>'
            )

        # ── Text block (centered, first line largest) ──────────────────────────
        # Compute per-line sizes, then stack them as a vertically-centered column.
        # Line box height ≈ size * 1.18 (a touch of leading). The whole block is
        # centered inside the padding bounds (which back off further for a double
        # border so text never collides with the inner ring).
        border_pad = (7.0 + 3.0) if double_border else 0.0  # inner ring + its stroke
        h_inset = inset + border_pad + 16.0   # horizontal text padding
        v_inset = inset + border_pad + 12.0   # vertical text padding
        usable_top = v_inset
        usable_h = _H - 2 * v_inset
        usable_w = _W - 2 * h_inset

        # Per line: pick a base size by length, then shrink it to fit the width
        # (CJK glyphs are full-width, so this is what keeps a Chinese company name
        # inside the border). First line stays largest.
        sizes = [
            _fit_width(ln, _line_font_size(ln, first=(i == 0)), usable_w)
            for i, ln in enumerate(lines)
        ]
        leading = 1.18
        line_heights = [s * leading for s in sizes]
        block_h = sum(line_heights)

        # If the stacked block is taller than the usable height, scale all sizes
        # down uniformly so it fits (deterministic: round to int after scaling).
        if block_h > usable_h and block_h > 0:
            scale = usable_h / block_h
            sizes = [max(10, int(s * scale)) for s in sizes]
            line_heights = [s * leading for s in sizes]
            block_h = sum(line_heights)

        # Baselines: center the block, then place each line's baseline at the
        # vertical center of its line box.
        block_top = usable_top + (usable_h - block_h) / 2.0
        tspans = ""
        cursor = block_top
        for ln, sz, lh in zip(lines, sizes, line_heights):
            baseline = cursor + lh / 2.0
            tspans += (
                f'<tspan font-size="{n(sz)}" x="{n(_CX)}" y="{n(baseline)}">'
                f'{svg.esc(ln)}</tspan>'
            )
            cursor += lh

        text_group = (
            f'<g font-family="{svg.esc_attr(latin_family)}" '
            f'font-weight="{weight}" fill="{fill}">'
            f'<text font-size="0" letter-spacing="0.5" text-anchor="middle" '
            f'dominant-baseline="central">{tspans}</text></g>'
        )

        svg_doc = (
            svg.svg_root(width=_W, height=_H, view_box_tuple=_VIEW_BOX)
            + border
            + text_group
            + "</svg>"
        )

        normalized = {
            "lines": lines,
            "preset": preset if (preset in _PRESETS) else _PRESET_NONE,
            "double_border": double_border,
            "color": fill,
            "weight": weight,
            "font": latin_prof.family,
            "zh_font": zh_prof.family,
            "line_font_sizes": sizes,
        }

        # Painted bbox ≈ the stroked outer rectangle (account for stroke width).
        half = sw_outer / 2.0
        painted = (ox - half, oy - half, ow + sw_outer, oh + sw_outer)

        return StyleResult(
            svg=svg_doc,
            normalized_params=normalized,
            warnings=warnings,
            fonts_used=fonts_used,
            view_box=_VIEW_BOX,
            painted_bbox=painted,
            canonical_size_mm=(38.0, 21.0),
            style_id="western.text",
            style_version=_VERSION,
        )


STYLE = _WesternText()

"""Minimal geometry helpers.

STAMP4U builds its rings and text paths as literal SVG arc strings, so almost no
geometry lives here. We expose only the two primitives a style author would
otherwise re-derive by hand:

  * :func:`ellipse_ring_path` — a filled annulus (outer ellipse minus inner),
    using the even-odd / opposite-sweep trick STAMP4U uses for its border bands.
  * :func:`ellipse_textpath` — a closed ellipse path suitable as a ``<textPath>``
    target, with a controllable sweep direction (top text runs clockwise,
    bottom text counter-clockwise so it reads upright).

Both return path-data strings built through :mod:`core.svg` so numbers are
formatted deterministically. Add to this module only when a concrete style
needs a shape that cannot be expressed inline — do not pre-build geometry.
"""

from __future__ import annotations

import math

from . import svg


def radial_arc_text(
    cx: float, cy: float, radius: float, text: str, font_size: float,
    *, fill: str, family: str, weight: int,
    max_span_deg: float = 210.0, center_deg: float = 0.0,
    spacing_factor: float = 1.16,
) -> tuple[str, float]:
    """Lay CJK characters around an arc the way a real Chinese seal does.

    Unlike a ``<textPath>`` (which tangent-shears each glyph so flank characters
    tip onto their sides — fine for Latin, wrong for CJK), this places every
    character individually and rotates it to stand **radially upright**: the
    glyph's vertical axis points outward from the centre, feet inward. A char at
    12 o'clock is upright; one at 3 o'clock is turned 90° so its top faces right.

    Characters read left-to-right across the top, centred on ``center_deg`` (0 =
    12 o'clock, measured clockwise). Spacing is ``spacing_factor·font_size`` of
    arc length per character; the total span is capped at ``max_span_deg`` so a
    long name tightens rather than wrapping down the sides, and a short name
    clusters at the top instead of being force-spread across a fixed arc.

    The caller owns clearance: ``radius`` is where glyph CENTRES sit, so keep
    ``radius + font_size/2`` inside the inner border. Returns ``(svg_group,
    span_deg)`` — the span lets a caller keep clear of a bottom element.
    """
    n = svg.num
    chars = list(text)
    m = len(chars)
    if m == 0:
        return "", 0.0
    if m == 1:
        angles = [center_deg]
        span = 0.0
    else:
        step = math.degrees((font_size * spacing_factor) / radius)
        span = step * (m - 1)
        if span > max_span_deg:
            step = max_span_deg / (m - 1)
            span = max_span_deg
        start = center_deg - span / 2.0
        angles = [start + i * step for i in range(m)]

    glyphs = []
    for ch, phi in zip(chars, angles):
        rad = math.radians(phi)
        x = cx + radius * math.sin(rad)
        y = cy - radius * math.cos(rad)
        glyphs.append(
            f'<text x="{n(x)}" y="{n(y)}" font-size="{n(font_size)}" '
            f'text-anchor="middle" dominant-baseline="central" '
            f'transform="rotate({n(phi)},{n(x)},{n(y)})">{svg.esc(ch)}</text>'
        )
    group = (
        f'<g font-family="{svg.esc_attr(family)}" font-weight="{weight}" '
        f'fill="{fill}">{"".join(glyphs)}</g>'
    )
    return group, span


def ellipse_ring_path(cx: float, cy: float, outer_rx: float, outer_ry: float,
                      inner_rx: float, inner_ry: float) -> str:
    """Path data for a filled elliptical ring (annulus).

    The outer contour sweeps one way and the inner contour the opposite way so a
    nonzero/even-odd fill leaves the middle hollow — exactly STAMP4U's border
    band idiom. Returns just the ``d`` string (no element)."""
    n = svg.num
    return (
        f"M {n(cx)},{n(cy)} m -{n(outer_rx)},0 "
        f"a {n(outer_rx)},{n(outer_ry)} 0 1,1 {n(2 * outer_rx)},0 "
        f"a {n(outer_rx)},{n(outer_ry)} 0 1,1 -{n(2 * outer_rx)},0 z "
        f"M {n(cx)},{n(cy)} m -{n(inner_rx)},0 "
        f"a {n(inner_rx)},{n(inner_ry)} 0 1,0 {n(2 * inner_rx)},0 "
        f"a {n(inner_rx)},{n(inner_ry)} 0 1,0 -{n(2 * inner_rx)},0 z"
    )


def ellipse_textpath(cx: float, cy: float, rx: float, ry: float,
                    *, clockwise: bool) -> str:
    """Path data for a closed ellipse used as a ``<textPath>`` baseline.

    ``clockwise=True`` makes text centered at ``startOffset=50%`` sit along the
    TOP arc reading left-to-right; ``clockwise=False`` puts it along the BOTTOM
    arc, also upright. Mirrors STAMP4U's ``oval-patha`` (sweep flag 1) and
    ``oval-patha2`` (sweep flag 0). Returns just the ``d`` string."""
    n = svg.num
    if clockwise:
        # start at bottom, sweep flag 1 — text centers at the top
        return (
            f"M {n(cx)},{n(cy + ry)} "
            f"a {n(rx)},{n(ry)} 0 0,1 -{n(rx)},-{n(ry)} "
            f"a {n(rx)},{n(ry)} 0 0,1 {n(rx)},-{n(ry)} "
            f"a {n(rx)},{n(ry)} 0 0,1 {n(rx)},{n(ry)} "
            f"a {n(rx)},{n(ry)} 0 0,1 -{n(rx)},{n(ry)} z"
        )
    # start at top, sweep flag 0 — text centers at the bottom, upright
    return (
        f"M {n(cx)},{n(cy - ry)} "
        f"a {n(rx)},{n(ry)} 0 0,0 -{n(rx)},{n(ry)} "
        f"a {n(rx)},{n(ry)} 0 0,0 {n(rx)},{n(ry)} "
        f"a {n(rx)},{n(ry)} 0 0,0 {n(rx)},-{n(ry)} "
        f"a {n(rx)},{n(ry)} 0 0,0 -{n(rx)},-{n(ry)} z"
    )

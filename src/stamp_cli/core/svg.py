"""SVG string helpers — deterministic, byte-stable output.

Two jobs:
  1. XML-escape user text so company names with ``&``/``<``/``"`` cannot break
     the document (or inject markup).
  2. Format floats with a fixed number of decimals so the SAME params always
     produce the SAME bytes. STAMP4U's formulas yield values like ``197 - 5*38/6
     = 165.333…``; left to ``str(float)`` these vary in length and trailing
     digits across platforms. We pin them.

Everything here is pure and side-effect free.
"""

from __future__ import annotations

# Decimal places kept when formatting coordinates / sizes into path data and
# attributes. 3 is plenty for sub-pixel SVG geometry and keeps strings short.
NUM_DECIMALS = 3


def esc(text: object) -> str:
    """Escape a value for use in XML *element content*.

    Replaces ``&``, ``<``, ``>``. Safe for text nodes and tspans.
    """
    s = str(text)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def esc_attr(text: object) -> str:
    """Escape a value for use inside a double-quoted XML *attribute*.

    Adds quote escaping on top of :func:`esc` so the value can never terminate
    the attribute early.
    """
    return esc(text).replace('"', "&quot;").replace("'", "&#39;")


def num(value: float | int) -> str:
    """Format a number deterministically for SVG output.

    - Fixed to :data:`NUM_DECIMALS` decimals, then trailing zeros (and a bare
      trailing dot) are stripped so ``170.000`` -> ``170`` and ``165.333`` stays
      ``165.333``.
    - ``-0`` is normalized to ``0``.

    The result is byte-stable for a given input regardless of platform float
    repr quirks.
    """
    f = float(value)
    if f == 0:  # collapse -0.0 and 0.0
        return "0"
    s = f"{f:.{NUM_DECIMALS}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    # ``-0`` can survive the rstrip path (e.g. "-0.000" -> "-0"); fix it.
    if s in ("-0", "-"):
        return "0"
    return s


def fmt(*values: float | int) -> str:
    """Format several numbers and join with single spaces (path-data friendly)."""
    return " ".join(num(v) for v in values)


def view_box(min_x: float, min_y: float, width: float, height: float) -> str:
    """Build a ``viewBox`` attribute value from its four components."""
    return fmt(min_x, min_y, width, height)


def svg_root(
    *,
    width: float,
    height: float,
    view_box_tuple: tuple[float, float, float, float],
    xlink: bool = True,
) -> str:
    """Open an ``<svg>`` root element with deterministic attributes.

    ``view_box_tuple`` is ``(min_x, min_y, width, height)``. ``xlink`` adds the
    xlink namespace declaration (STAMP4U templates declare it even though they
    use the modern ``href`` attribute on ``<textPath>``).
    """
    ns = (
        ' xmlns:xlink="http://www.w3.org/1999/xlink"' if xlink else ""
    )
    return (
        '<svg version="1.1" xmlns="http://www.w3.org/2000/svg"'
        f"{ns}"
        f' width="{num(width)}" height="{num(height)}"'
        f' viewBox="{view_box(*view_box_tuple)}">'
    )

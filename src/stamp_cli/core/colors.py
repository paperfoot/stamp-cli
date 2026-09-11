"""Stamp ink colors.

Two families of presets coexist:

  * **STAMP4U palette** — the exact colors stamp4u.hk emits, so our HK styles
    match pixel-for-pixel. ``red`` here is pure ``#FF0000`` (their default).
  * **Cinnabar / ink presets** — 朱砂 vermilion and friends from the original
    Pillow prototype, kept as named options for users who want a realistic
    ink-pad look rather than STAMP4U parity.

Because both families share the name ``red`` we keep them in *separate* dicts
and resolve STAMP4U first, then fall back to ink presets. So ``red`` ->
``#FF0000`` (STAMP4U), while ``vermilion`` / ``cinnabar`` -> the ink red.

Everything resolves to ``#RRGGBB`` (lowercase) — the form an SVG ``fill``
wants — and an RGB tuple is available via :func:`parse_rgb`.
"""

from __future__ import annotations

import re

# ── STAMP4U palette (verbatim from their COLORS map; see STAMP4U-EXTRACTED.md) ─
# Values are CSS strings exactly as STAMP4U uses them.
STAMP4U: dict[str, str] = {
    "red": "#FF0000",
    "blue": "#0220c7",
    "purple": "#8216db",
    "black": "#000000",  # STAMP4U uses the keyword "black"; we normalize to hex
}

# ── Ink-pad presets (RGB) — realistic chop inks from the original prototype ───
# Kept available by name. Cinnabar/vermilion is the classic 朱砂 seal red.
INK_RGB: dict[str, tuple[int, int, int]] = {
    "cinnabar": (200, 22, 29),     # 朱砂 — the classic seal red
    "vermilion": (200, 22, 29),
    "vermillion": (200, 22, 29),
    "scarlet": (178, 34, 34),
    "darkred": (139, 0, 0),
    "navy": (10, 35, 80),
    "ink-black": (15, 15, 15),     # softer than pure 0 — looks like real ink
    "green": (0, 102, 51),
    "gold": (180, 134, 60),
}

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_HEX_SHORT_RE = re.compile(r"^#?([0-9a-fA-F]{3})$")


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def parse(spec: str) -> str:
    """Resolve a color spec to a lowercase ``#rrggbb`` string for SVG ``fill``.

    Resolution order:
      1. STAMP4U palette (so ``red`` == ``#FF0000`` for HK parity)
      2. Ink-pad presets (``vermilion``, ``cinnabar``, ``navy`` …)
      3. ``#RRGGBB`` / ``RRGGBB`` / ``#RGB`` hex literals

    Raises ``ValueError`` with the list of presets on anything unknown.
    """
    s = spec.strip().lower()
    if s in STAMP4U:
        return STAMP4U[s].lower()
    if s in INK_RGB:
        return _rgb_to_hex(INK_RGB[s])
    if m := _HEX_RE.match(s):
        return "#" + m.group(1).lower()
    if m := _HEX_SHORT_RE.match(s):
        h = m.group(1).lower()
        return "#" + h[0] * 2 + h[1] * 2 + h[2] * 2
    raise ValueError(
        f"Unknown color '{spec}'. Use a preset ({', '.join(names())}) "
        f"or a hex string like #FF0000."
    )


def parse_rgb(spec: str) -> tuple[int, int, int]:
    """Same resolution as :func:`parse`, returned as an ``(r, g, b)`` tuple."""
    h = parse(spec)[1:]
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def names() -> list[str]:
    """Sorted list of every preset name (both families)."""
    return sorted(set(STAMP4U) | set(INK_RGB))


def listing() -> list[tuple[str, str, str]]:
    """Return ``[(name, hex, family)]`` for display in ``stamp colors``."""
    rows: list[tuple[str, str, str]] = []
    for name, css in STAMP4U.items():
        rows.append((name, parse(name), "stamp4u"))
    for name in INK_RGB:
        rows.append((name, parse(name), "ink"))
    return sorted(rows, key=lambda r: (r[2], r[0]))

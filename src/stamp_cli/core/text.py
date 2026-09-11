"""Fit real glyph bounds, including script overhangs, to a bounded text area."""
from __future__ import annotations

from functools import lru_cache

from fontTools.ttLib import TTFont
from PIL import ImageFont

from . import svg


@lru_cache(maxsize=64)
def _coverage(path, index, digest):
    with TTFont(path, fontNumber=index, lazy=True) as font:
        return frozenset((font.getBestCmap() or {}).keys())


def text_font(text, profiles):
    points = {ord(c) for c in text if not c.isspace()}
    for profile in profiles:
        if points <= _coverage(profile.file_path, profile.face_index, profile.sha256):
            return profile
    raise ValueError("The selected fonts cannot render this text. Choose a font with these characters using --font or --script-font.")


def fitted_text(text, profiles, box, *, size, minimum=10, color="#242A30", align="left"):
    """Return an SVG text node and its measured size, without clipping/shrinking indefinitely."""
    if not text:
        return "", size
    text = " ".join(text.split())
    profile = text_font(text, profiles)
    x, y, width, height = box
    def measure(points):
        face = ImageFont.truetype(profile.file_path, points * 4, index=profile.face_index)
        bounds = tuple(v / 4 for v in face.getbbox(text, anchor="ls"))
        return face, bounds
    face, bounds = measure(size)
    for _ in range(4):
        left, top, right, bottom = bounds
        ratio = min(1, width / max(1, right - left), height / max(1, bottom - top))
        if ratio == 1:
            break
        if size <= minimum:
            raise ValueError("Text is too long to fit legibly. Shorten the text or use a more compact font.")
        size = max(minimum, size * ratio * .985)
        face, bounds = measure(size)
    left, top, right, bottom = bounds
    if right - left > width or bottom - top > height:
        raise ValueError("Text is too long to fit legibly. Shorten the text or use a more compact font.")
    tx = x - left + ((width - (right - left)) / 2 if align == "center" else 0)
    ty = y + (height - (bottom - top)) / 2 - top
    variant = face.getname()[1].lower()
    weight = "700" if "bold" in variant else "400"
    style = "italic" if "italic" in variant or "oblique" in variant else "normal"
    return (f'<text x="{svg.num(tx)}" y="{svg.num(ty)}" '
            f'font-family="{svg.esc_attr(profile.family)}" font-size="{svg.num(size)}" '
            f'font-weight="{weight}" font-style="{style}" '
            f'fill="{color}" xml:space="preserve">{svg.esc(text)}</text>'), size

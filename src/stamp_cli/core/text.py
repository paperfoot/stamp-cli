"""Fit real glyph bounds, including script overhangs, to a bounded text area."""
from __future__ import annotations

from functools import lru_cache
from dataclasses import replace
import math
import unicodedata

from fontTools.ttLib import TTFont, TTCollection
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from PIL import ImageFont

from . import svg


@lru_cache(maxsize=64)
def _weight_face(path, family, digest, requested, current_index):
    """Measure the same family/weight that SVG selects from a collection."""
    if not path.lower().endswith('.ttc'):
        return None
    with TTCollection(path, lazy=True) as collection:
        current = collection.fonts[current_index]['OS/2']
        candidates = []
        for index, font in enumerate(collection.fonts):
            names = font['name']
            if family in (names.getDebugName(16), names.getDebugName(1)):
                face = font['OS/2']
                candidates.append((bool((face.fsSelection ^ current.fsSelection) & 1),
                                   abs(face.usWidthClass - current.usWidthClass),
                                   abs(face.usWeightClass - requested), index))
        return min(candidates)[-1] if candidates else None


def weighted_font(profile, weight):
    index = _weight_face(profile.file_path, profile.family, profile.sha256, weight, profile.face_index)
    return replace(profile, face_index=index) if index is not None else profile


@lru_cache(maxsize=64)
def _face_style(path, index, digest):
    with TTFont(path, fontNumber=index, lazy=True) as font:
        face = font['OS/2']
        weight = face.usWeightClass
        style = 'italic' if face.fsSelection & 1 else 'normal'
        widths = ('ultra-condensed', 'extra-condensed', 'condensed', 'semi-condensed',
                  'normal', 'semi-expanded', 'expanded', 'extra-expanded', 'ultra-expanded')
        return weight, style, widths[max(1, min(9, face.usWidthClass)) - 1]


def font_attributes(profile):
    """Select the measured face in SVG, including nonstandard collection weights."""
    weight, style, stretch = _face_style(profile.file_path, profile.face_index, profile.sha256)
    return f'font-weight="{weight}" font-style="{style}" font-stretch="{stretch}"'


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


def fitted_text(text, profiles, box, *, size, minimum=10, color="#242A30", align="left", spacing=0):
    """Return an SVG text node and its measured size, without clipping/shrinking indefinitely."""
    if not text:
        return "", size
    text = " ".join(unicodedata.normalize('NFC', text).split())
    if not math.isfinite(spacing) or not 0 <= spacing <= 12:
        raise ValueError('Letter spacing must be between 0 and 12 units.')
    profile = text_font(text, profiles)
    x, y, width, height = box
    def measure(points):
        face = ImageFont.truetype(profile.file_path, points * 4, index=profile.face_index)
        left, top, right, bottom = (v / 4 for v in face.getbbox(text, anchor="ls"))
        bounds = left, top, right + spacing * max(0, len(text) - 1), bottom
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
    return (f'<text x="{svg.num(tx)}" y="{svg.num(ty)}" '
            f'font-family="{svg.esc_attr(profile.family)}" font-size="{svg.num(size)}" '
            f'{font_attributes(profile)} '
            f'letter-spacing="{svg.num(spacing)}" '
            f'fill="{color}" xml:space="preserve">{svg.esc(text)}</text>'), size


def fitted_block(lines, box, *, gap=12, minimum=14, color="#242A30", ellipse=None):
    """Centre a complete text block by its ink bounds, with explicit interline gaps.

    Each line is (text, font profiles, maximum size, letter spacing).
    """
    x, y, width, height = box
    lines = [(' '.join(unicodedata.normalize('NFC', text).split()), profiles, size, spacing)
             for text, profiles, size, spacing in lines if text.strip()]
    if not lines:
        return '', []
    fitted = []
    for text, profiles, size, spacing in lines:
        _, actual = fitted_text(text, profiles, (0, 0, width, height), size=size,
                                minimum=minimum, spacing=spacing)
        profile = text_font(text, profiles)
        fitted.append([text, profile, actual, spacing])

    def ink_heights():
        result = []
        for text, profile, size, _ in fitted:
            face = ImageFont.truetype(profile.file_path, size * 4, index=profile.face_index)
            _, top, _, bottom = face.getbbox(text, anchor='ls')
            result.append((bottom - top) / 4)
        return result

    heights = ink_heights()
    available = height - gap * (len(lines) - 1)
    if sum(heights) > available:
        scale = available / sum(heights) * .99
        for line in fitted:
            line[2] *= scale
            if line[2] < minimum:
                raise ValueError('Too many lines to fit legibly. Shorten the text or use fewer lines.')
        heights = ink_heights()
    if ellipse:
        # Refit each line to its actual chord, then recenter the complete block.
        # This preserves useful size without assuming all rectangle corners
        # will remain empty when the user changes a name or adds another line.
        cx, cy, rx, ry = ellipse
        for _ in range(8):
            cursor = y + (height - sum(heights) - gap * (len(lines) - 1)) / 2
            changed = False
            for line, ink_height in zip(fitted, heights):
                far = max(abs(cursor - cy), abs(cursor + ink_height - cy))
                if far >= ry:
                    raise ValueError('Too many lines to fit inside the seal. Use fewer lines.')
                chord = min(width, 2 * rx * math.sqrt(1 - (far / ry) ** 2))
                _, actual = fitted_text(line[0], [line[1]], (cx - chord / 2, cursor, chord, ink_height),
                                        size=line[2], minimum=minimum, spacing=line[3])
                changed |= actual < line[2]
                line[2] = actual
                cursor += ink_height + gap
            heights = ink_heights()
            if not changed:
                break
        else:
            raise ValueError('Text cannot fit cleanly inside the seal. Shorten a line.')
    cursor = y + (height - sum(heights) - gap * (len(lines) - 1)) / 2
    elements, sizes = [], []
    for (text, profile, size, spacing), ink_height in zip(fitted, heights):
        node, actual = fitted_text(text, [profile], (x, cursor, width, ink_height),
                                  size=size, minimum=minimum, color=color,
                                  align='center', spacing=spacing)
        elements.append(node)
        sizes.append(actual)
        cursor += ink_height + gap
    return ''.join(elements), sizes


def fitted_symbol(symbol, profiles, box, *, size=34, color="#242A30"):
    """Outline a single decorative glyph so every SVG renderer paints it.

    Symbol-only fonts can be rejected as a primary text face by resvg. A glyph
    outline avoids fallback substitution and centres the actual vector bounds.
    """
    if len(symbol) != 1 or symbol.isspace():
        raise ValueError('--star-glyph must be one visible character.')
    profile = text_font(symbol, profiles)
    with TTFont(profile.file_path, fontNumber=profile.face_index, lazy=True) as font:
        glyphs = font.getGlyphSet()
        glyph = glyphs[font.getBestCmap()[ord(symbol)]]
        bounds = BoundsPen(glyphs)
        glyph.draw(bounds)
        if bounds.bounds is None:
            raise ValueError('--star-glyph must have a visible outline.')
        left, bottom, right, top = bounds.bounds
        path = SVGPathPen(glyphs)
        glyph.draw(path)
        x, y, width, height = box
        scale = min(size / font['head'].unitsPerEm,
                    width / (right - left), height / (top - bottom))
        tx = x + (width - (right - left) * scale) / 2 - left * scale
        ty = y + (height - (top - bottom) * scale) / 2 + top * scale
        return (f'<path aria-label="{svg.esc_attr(symbol)}" fill="{color}" '
                f'transform="translate({svg.num(tx)} {svg.num(ty)}) '
                f'scale({scale:.8f} {-scale:.8f})" d="{path.getCommands()}"/>')

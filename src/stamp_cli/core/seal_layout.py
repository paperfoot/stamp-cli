"""Measured layouts for oval, circular, and rectangular business stamps.

Geometry is authored in physical-aspect canvases. Text uses the selected font's
metrics rather than character-count tables; borders do not change with a name.
"""
from __future__ import annotations

import math
import unicodedata

from PIL import ImageFont

from . import svg, colors
from .fonts import default_resolver
from .text import fitted_text, fitted_symbol, text_font, weighted_font, font_attributes
from ..styles.base import StyleResult


def ellipse(cx, cy, rx, ry, ink, stroke=2):
    return (f'<ellipse cx="{svg.num(cx)}" cy="{svg.num(cy)}" '
            f'rx="{svg.num(rx)}" ry="{svg.num(ry)}" fill="none" '
            f'stroke="{ink}" stroke-width="{svg.num(stroke)}"/>')


def star(cx, cy, radius, ink):
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        r = radius if i % 2 == 0 else radius * (3 - math.sqrt(5)) / 2
        points.append(f'{svg.num(cx + r * math.cos(angle))},{svg.num(cy + r * math.sin(angle))}')
    return f'<polygon points="{" ".join(points)}" fill="{ink}"/>'


def _offset_arc(cx, cy, rx, ry, offset, bottom, sweep=200):
    """A baseline parallel to the visible-ink centre, including ellipse shoulders.

    Equal changes to ellipse radii are not a normal offset. Sample the true
    normals at one-degree intervals (subpixel error at supported print sizes).
    """
    start, end = ((90 + sweep / 2, 90 - sweep / 2) if bottom
                  else (-90 - sweep / 2, -90 + sweep / 2))
    points = []
    for step in range(201):
        angle = math.radians(start + (end - start) * step / 200)
        co, si = math.cos(angle), math.sin(angle)
        nx, ny = co / rx, si / ry
        norm = math.hypot(nx, ny)
        points.append((cx + rx * co + offset * nx / norm,
                       cy + ry * si + offset * ny / norm))
    length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
    path = 'M ' + ' L '.join(f'{svg.num(x)} {svg.num(y)}' for x, y in points)
    return path, length


def arc_text(text, profiles, cx, cy, rx, ry, *, ink, size, key, weight=700,
             bottom=False, spacing=1.5, band_width=52, sweep=200):
    """Centre visible letter ink in a ring band, then fit the natural advances.

    rx/ry locate the ink centre, not the alphabetic baseline. Tracking changes
    the run's span, never the glyph aspect ratio. Both arc ends keep clear space.
    """
    if not text:
        return '', 0.
    text = ' '.join(unicodedata.normalize('NFC', text).split())
    profile = text_font(text, profiles)
    if not math.isfinite(size) or not 14 <= size <= 96:
        raise ValueError('Arc font size must be between 14 and 96 units.')
    if not math.isfinite(spacing) or not 0 <= spacing <= 12:
        raise ValueError('Arc letter spacing must be between 0 and 12 units.')

    def measure(points):
        face = ImageFont.truetype(profile.file_path, points * 4, index=profile.face_index)
        left, top, right, bottom_ink = (v / 4 for v in face.getbbox(text, anchor='ls'))
        midpoint = (top + bottom_ink) / 2
        path, length = _offset_arc(cx, cy, rx, ry, -midpoint if bottom else midpoint, bottom, sweep)
        advance = face.getlength(text) / 4
        width = max(advance, right - left) + spacing * max(0, len(text) - 1)
        fits = width <= length - 16 and bottom_ink - top <= band_width - 18
        return fits, path, advance, left, right, face

    minimum, maximum = 14., float(size)
    if not measure(minimum)[0]:
        raise ValueError('Company name is too long to fit legibly on the arc. Shorten it, reduce spacing, or use an abbreviation.')
    if not measure(maximum)[0]:
        for _ in range(18):
            middle = (minimum + maximum) / 2
            if measure(middle)[0]:
                minimum = middle
            else:
                maximum = middle
        size = minimum
    _, path, advance, left, right, face = measure(size)
    # text-anchor centres advances; account for the run's visible side bearings.
    bearing = (advance - left - right) / 2
    node = (f'<defs><path id="{key}" d="{path}"/></defs>'
            f'<text font-family="{svg.esc_attr(profile.family)}" font-size="{svg.num(size)}" '
            f'{font_attributes(profile)} '
            f'letter-spacing="{svg.num(spacing)}" fill="{ink}" dx="{svg.num(bearing)}">'
            f'<textPath href="#{key}" startOffset="50%" text-anchor="middle">'
            f'{svg.esc(text)}</textPath></text>')
    return node, size


def _star_label(text, profiles, cx, cy, rx, ry, star_radius, *, below, size, spacing, ink):
    """Fit visible label corners inside the circle and clear of the star."""
    profile = text_font(text, profiles)
    edge = (cy + star_radius * math.cos(math.pi / 5) + 12 if below
            else cy - star_radius - 12)

    def place(points):
        face = ImageFont.truetype(profile.file_path, points * 4, index=profile.face_index)
        _, top, _, bottom = face.getbbox(text, anchor='ls')
        height = (bottom - top) / 4
        y = edge if below else edge - height
        far = max(abs(y - cy), abs(y + height - cy))
        if far >= ry:
            raise ValueError('No room beside star.')
        width = 2 * rx * math.sqrt(1 - (far / ry) ** 2)
        return fitted_text(text, profiles, (cx - width / 2, y, width, height),
                           size=points, minimum=points, spacing=spacing,
                           color=ink, align='center')

    low, high = 14., size
    try:
        result = place(low)
    except ValueError:
        raise ValueError('Name and centre star cannot fit legibly. Reduce --prc-star-size, shorten the name, or use --no-prc-star.') from None
    try:
        return place(high)
    except ValueError:
        for _ in range(18):
            middle = (low + high) / 2
            try:
                result = place(middle)
                low = middle
            except ValueError:
                high = middle
        return result


def company_seal(style, p, *, oval):
    en, zh1, zh2 = (' '.join(unicodedata.normalize('NFC', str(p[k])).split())
                    for k in ('en', 'zh_line1', 'zh_line2'))
    if not (en or zh1 or zh2) or (oval and not en):
        raise ValueError(f'{style.META.id} requires a company name.')
    ink = colors.parse(str(p['color']))
    weight = int(p['weight'])
    if not 100 <= weight <= 900:
        raise ValueError('--weight must be between 100 and 900.')
    latin = weighted_font(default_resolver.resolve(str(p['en_font'])), weight)
    cjk = weighted_font(default_resolver.resolve(str(p['zh_font'])), weight)
    fonts = [latin, cjk]
    bottom = str(p.get('en_bottom', '')).strip()
    mark = str(p['star_glyph']) if p['star'] and not bottom else ''
    if mark:
        fonts.append(default_resolver.symbols2())
    w, h = (480., 320.) if oval else (420., 420.)
    cx, cy = w / 2, h / 2
    outer_rx, outer_ry = cx - 11, cy - 11
    inner_rx, inner_ry = (163., 85.) if oval else (135., 135.)
    # Midpoint between the facing ink edges, including both stroke widths.
    arc_rx = (outer_rx - 10 - .75 + inner_rx + 1) / 2
    arc_ry = (outer_ry - 10 - .75 + inner_ry + 1) / 2
    parts = [ellipse(cx, cy, outer_rx, outer_ry, ink, 5),
             ellipse(cx, cy, outer_rx - 10, outer_ry - 10, ink, 1.5),
             ellipse(cx, cy, inner_rx, inner_ry, ink, 2)]
    desired = float(p.get('en_size') or p.get('font_size') or 36)
    desired_zh = float(p.get('zh_size') or 44)
    if not math.isfinite(desired_zh) or not 14 <= desired_zh <= 96:
        raise ValueError('Chinese font size must be between 14 and 96 units, or 0 for automatic sizing.')
    spacing = float(p['en_spacing']) if p.get('en_spacing') is not None else 1.5
    zh_spacing = float(p.get('zh_spacing', 1))
    bottom_spacing = float(p['en_bottom_spacing']) if p.get('en_bottom_spacing') is not None else spacing
    if any(not math.isfinite(value) or not 0 <= value <= 12
           for value in (spacing, zh_spacing, bottom_spacing)):
        raise ValueError('Letter spacing must be finite and between 0 and 12 units.')
    top, fs = arc_text(en, [latin], cx, cy, arc_rx, arc_ry, ink=ink,
                       size=desired, key='oval-patha' if oval else 'company-top',
                       weight=weight, spacing=spacing, sweep=176 if bottom else 200)
    parts.append(top)
    if bottom:
        el, _ = arc_text(bottom, [latin], cx, cy, arc_rx, arc_ry,
                         ink=ink, size=28, key='company-bottom', weight=weight, bottom=True,
                         spacing=bottom_spacing, sweep=176)
        parts.append(el)
    elif mark:
        parts.append(fitted_symbol(mark, fonts, (cx - 38, cy + arc_ry - 16, 76, 32),
                                   size=34, color=ink))
    central_star = bool(p.get('prc_star'))
    if central_star:
        mm = float(p.get('prc_star_size', 14))
        if not math.isfinite(mm) or not 2 <= mm <= 18:
            raise ValueError('--prc-star-size must be between 2 and 18 mm.')
        parts.append(star(cx, cy, mm * 5, ink))
    lines = [line for line in (zh1, zh2) if line]
    sizes = []
    for i, line in enumerate(lines):
        y = cy - 24 if len(lines) == 1 else cy - 54 + i * 60
        if central_star:
            el, actual = _star_label(line, [cjk, latin], cx, cy, inner_rx - 12, inner_ry - 12,
                                    mm * 5, below=i > 0, size=desired_zh,
                                    spacing=zh_spacing, ink=ink)
        else:
            far = max(abs(y - cy), abs(y + 48 - cy))
            half_width = min(inner_rx - 18,
                             (inner_rx - 10) * math.sqrt(1 - (far / (inner_ry - 10)) ** 2))
            el, actual = fitted_text(line, [cjk, latin], (cx - half_width, y, 2 * half_width, 48),
                                     size=desired_zh, minimum=14, color=ink,
                                     align='center', spacing=zh_spacing)
        parts.append(el)
        sizes.append(actual)
    normalized = {**p, 'en': en, 'zh_line1': zh1, 'zh_line2': zh2, 'color': ink,
                  'english_font_size': fs, 'english_letter_spacing': spacing,
                  'english_bottom_letter_spacing': bottom_spacing, 'chinese_letter_spacing': zh_spacing,
                  'arc_ink_center_radii': [arc_rx, arc_ry],
                  'en_font': latin.family, 'zh_font': cjk.family,
                  'zh_line1_font_size': sizes[0] if sizes else 0,
                  'zh_line2_font_size': sizes[-1] if len(sizes) > 1 else 0}
    view = (0., 0., w, h)
    return StyleResult(svg=svg.svg_root(width=w, height=h, view_box_tuple=view) + ''.join(parts) + '</svg>',
                       normalized_params=normalized, warnings=[], fonts_used=fonts,
                       view_box=view, painted_bbox=(8., 8., w - 16, h - 16),
                       canonical_size_mm=(45., 30.) if oval else (42., 42.),
                       style_id=style.META.id, style_version='4')


RECT_PRESETS = {
    'sign': dict(line1='Example Company Limited', line2='示例有限公司',
                 signature_top='For and on behalf of', signature_bottom='Authorised signature', signature_line=True),
    'address': dict(line1='Example Company Limited', line2='Registered office address',
                    signature_top='', signature_bottom='', signature_line=False),
    'cheque': dict(line1='Pay to', line2='Example Company Limited',
                   signature_top='', signature_bottom='', signature_line=False),
    'certified-true-copy': dict(line1='CERTIFIED TRUE COPY', line2='核證副本無訛',
                               signature_top='', signature_bottom='', signature_line=False),
}


def rectangular_seal(style, params):
    p = {**style.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
    preset = RECT_PRESETS[p['preset']]
    for key, value in preset.items():
        if key not in params or params[key] is None:
            p[key] = value
    ink = colors.parse(p['color'])
    fonts = [default_resolver.resolve(p['en_font']), default_resolver.resolve(p['zh_font'])]
    parts, y, line_sizes = [], 12., []
    def add(text, size, gap, centered=False):
        nonlocal y
        if not str(text).strip():
            return
        for line in str(text).splitlines():
            node, actual = fitted_text(line, fonts, (14, y, 332, size * 1.4),
                                       size=size, minimum=11, color=ink,
                                       align='center' if centered else 'left')
            parts.append(node)
            line_sizes.append(actual)
            y += size * 1.4 + gap
    add(p['signature_top'], 18, 6)
    add(p['line1'], 26, 3)
    add(p['line2'], 22 if p['preset'] != 'address' else 17, 5)
    if p['signature_line']:
        y += 31
        parts.append(f'<path d="M 14 {svg.num(y)} H 346" stroke="{ink}" stroke-width="1.2" stroke-dasharray="3 3"/>')
        y += 7
    add(p['signature_bottom'], 18, 0, centered=True)
    height = max(60., y + 10)
    if height > 600:
        raise ValueError('Stamp has too many lines. Keep addresses and signature captions concise.')
    view = (0., 0., 360., height)
    p.update(color=ink, en_font=fonts[0].family, zh_font=fonts[1].family, measured_font_sizes=line_sizes)
    return StyleResult(svg=svg.svg_root(width=360, height=height, view_box_tuple=view) + ''.join(parts) + '</svg>',
                       normalized_params=p, warnings=[], fonts_used=fonts, view_box=view,
                       painted_bbox=(14., 12., 332., height - 22), canonical_size_mm=(60., height / 6),
                       style_id=style.META.id, style_version='3')

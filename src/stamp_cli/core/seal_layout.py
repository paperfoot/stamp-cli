"""Measured layouts for oval, circular, and rectangular business stamps.

Geometry is authored in physical-aspect canvases. Text uses the selected font's
metrics rather than character-count tables; borders do not change with a name.
"""
from __future__ import annotations

import math

from PIL import ImageFont

from . import svg, colors
from .fonts import default_resolver
from .text import fitted_text, text_font
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


def arc_text(text, profiles, cx, cy, rx, ry, *, ink, size, key, weight=700,
             bottom=False, spacing=0):
    """Fit text to the central half of an ellipse with a bounded minimum size."""
    if not text:
        return '', 0.
    profile = text_font(text, profiles)
    if not 8 <= size <= 96 or not -2 <= spacing <= 12:
        raise ValueError('Arc font size must be 8–96 units and letter spacing −2–12 units.')
    # Ramanujan ellipse circumference; reserve a margin at each arc end.
    h = ((rx - ry) / (rx + ry)) ** 2
    available = math.pi * (rx + ry) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h))) * .46
    face = ImageFont.truetype(profile.file_path, size * 4, index=profile.face_index)
    advance = face.getlength(text) / 4
    total = advance + spacing * max(0, len(text) - 1)
    if total > available:
        size *= (available - spacing * max(0, len(text) - 1)) / max(1, advance)
    if size < 14:
        raise ValueError('Company name is too long to fit legibly on the arc. Shorten it or use an abbreviation.')
    # Start at a horizontal endpoint. Halfway follows the upper/lower crown.
    left, right = cx - rx, cx + rx
    if bottom:
        path = f'M {svg.num(left)} {svg.num(cy)} A {svg.num(rx)} {svg.num(ry)} 0 0 0 {svg.num(right)} {svg.num(cy)}'
    else:
        path = f'M {svg.num(left)} {svg.num(cy)} A {svg.num(rx)} {svg.num(ry)} 0 0 1 {svg.num(right)} {svg.num(cy)}'
    node = (f'<defs><path id="{key}" d="{path}"/></defs>'
            f'<text font-family="{svg.esc_attr(profile.family)}" font-size="{svg.num(size)}" '
            f'font-weight="{weight}" letter-spacing="{svg.num(spacing)}" fill="{ink}">'
            f'<textPath href="#{key}" startOffset="50%" text-anchor="middle">'
            f'{svg.esc(text)}</textPath></text>')
    return node, size


def company_seal(style, p, *, oval):
    en, zh1, zh2 = (str(p[k]).strip() for k in ('en', 'zh_line1', 'zh_line2'))
    if not (en or zh1 or zh2) or (oval and not en):
        raise ValueError(f'{style.META.id} requires a company name.')
    ink = colors.parse(str(p['color']))
    weight = int(p['weight'])
    if not 100 <= weight <= 900:
        raise ValueError('--weight must be between 100 and 900.')
    latin = default_resolver.resolve(str(p['en_font']))
    cjk = default_resolver.resolve(str(p['zh_font']))
    fonts = [latin, cjk]
    bottom = str(p.get('en_bottom', '')).strip()
    mark = str(p['star_glyph']) if p['star'] and not bottom else ''
    if mark:
        fonts.append(default_resolver.symbols2())
    w, h = (480., 320.) if oval else (420., 420.)
    cx, cy = w / 2, h / 2
    outer_rx, outer_ry = cx - 11, cy - 11
    inner_rx, inner_ry = (163., 85.) if oval else (135., 135.)
    arc_rx, arc_ry = (196., 114.) if oval else (162., 162.)
    parts = [ellipse(cx, cy, outer_rx, outer_ry, ink, 5),
             ellipse(cx, cy, outer_rx - 10, outer_ry - 10, ink, 1.5),
             ellipse(cx, cy, inner_rx, inner_ry, ink, 2)]
    desired = min(36., float(p.get('en_size') or p.get('font_size') or 36))
    spacing = float(p.get('en_spacing') or 0)
    top, fs = arc_text(en, [latin], cx, cy, arc_rx, arc_ry, ink=ink,
                       size=desired, key='oval-patha' if oval else 'company-top',
                       weight=weight, spacing=spacing)
    parts.append(top)
    if bottom:
        el, _ = arc_text(bottom, [latin], cx, cy, arc_rx, arc_ry,
                         ink=ink, size=28, key='company-bottom', weight=weight, bottom=True)
        parts.append(el)
    elif mark:
        el, _ = fitted_text(mark, fonts, (cx - 38, h - 57, 76, 32), size=34,
                            minimum=14, color=ink, align='center')
        parts.append(el)
    central_star = bool(p.get('prc_star'))
    if central_star:
        mm = float(p.get('prc_star_size', 14))
        if not math.isfinite(mm) or not 2 <= mm <= 18:
            raise ValueError('--prc-star-size must be between 2 and 18 mm.')
        parts.append(star(cx, cy, mm * 5, ink))
    lines = [line for line in (zh1, zh2) if line]
    sizes = []
    for i, line in enumerate(lines):
        y = cy - 25 if len(lines) == 1 else cy - 54 + i * 60
        if central_star:
            y = cy - 111 if i == 0 else cy + 78
        el, actual = fitted_text(line, [cjk, latin], (cx - inner_rx + 18, y, 2 * inner_rx - 36, 48),
                                 size=float(p.get('zh_size') or 44), minimum=14, color=ink, align='center')
        # Respect a requested weight for seal lettering, including synthetic bold.
        parts.append(el.replace('font-weight="400"', f'font-weight="{weight}"'))
        sizes.append(actual)
    normalized = {**p, 'en': en, 'zh_line1': zh1, 'zh_line2': zh2, 'color': ink,
                  'english_font_size': fs, 'english_letter_spacing': spacing,
                  'en_font': latin.family, 'zh_font': cjk.family,
                  'zh_line1_font_size': sizes[0] if sizes else 0,
                  'zh_line2_font_size': sizes[-1] if len(sizes) > 1 else 0}
    view = (0., 0., w, h)
    return StyleResult(svg=svg.svg_root(width=w, height=h, view_box_tuple=view) + ''.join(parts) + '</svg>',
                       normalized_params=normalized, warnings=[], fonts_used=fonts,
                       view_box=view, painted_bbox=(8., 8., w - 16, h - 16),
                       canonical_size_mm=(45., 30.) if oval else (42., 42.),
                       style_id=style.META.id, style_version='3')


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

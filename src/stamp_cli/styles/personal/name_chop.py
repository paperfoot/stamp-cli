"""Square name seals with measured characters in traditional reading order."""
from __future__ import annotations
import math
from ..base import ParamSpec, StyleMeta, StyleResult
from ...core import colors as colors_mod, svg
from ...core.fonts import default_resolver
from ...core.text import fitted_text

_DEFAULT_CORNER = 10

class _NameChop:
    META = StyleMeta(
        id="personal.name_chop",
        country="personal",
        shape="square",
        title="Personal square name chop (人名章)",
        description=(
            "Square personal name seal: rounded red border, white field, and the "
            "name carved in red read top-to-bottom, right-to-left (surname column "
            "on the right). 1–4 characters split into surname/given columns; "
            "longer strings pack into a near-square grid. --inverted gives a solid "
            "red field with white characters. Measured character cells."
        ),
        canonical_size_mm=(20.0, 20.0),
        reference="Traditional right-to-left name columns",
    )

    PARAMS = [
        ParamSpec(
            name="chars", type=str, default="",
            help="The name to engrave (e.g. 陳大文). 1–4 characters are laid out "
                 "as a surname column (right) + given-name column (left), read "
                 "right-to-left; longer strings pack into a near-square grid.",
        ),
        ParamSpec(
            name="surname", type=str, default="",
            help="Explicit right (surname) column, overriding the auto-split of "
                 "--chars. Read top-to-bottom.",
        ),
        ParamSpec(
            name="given", type=str, default="",
            help="Explicit left (given-name) column, overriding the auto-split "
                 "of --chars. Read top-to-bottom.",
        ),
        ParamSpec(
            name="inverted", type=bool, default=False,
            help="Solid red field with white characters (白文) instead of red "
                 "characters on a white field (朱文).",
        ),
        ParamSpec(
            name="corner_radius", type=int, default=_DEFAULT_CORNER,
            help="Corner radius of the border ("
                 "default 10).",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, blue, purple, black, vermilion…) or "
                 "#RRGGBB. Name chops are conventionally red (#FF0000).",
        ),
        ParamSpec(
            name="weight", type=int, default=600,
            help="Font weight for the characters (100–900).",
        ),
        ParamSpec(
            name="zh_font", type=str, default="song",
            help="Font alias for the characters (default Songti SC; a seal/篆書 "
                 "font reads most traditionally). "
                 "",
        ),
    ]

    DEFAULTS = {
        "chars": "",
        "surname": "",
        "given": "",
        "inverted": False,
        "corner_radius": _DEFAULT_CORNER,
        "color": "red",
        "weight": 600,
        "zh_font": "song",
    }

    def build_svg(self, **params) -> StyleResult:
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        chars, surname, given = (str(p[k]).strip() for k in ('chars', 'surname', 'given'))
        content = surname + given if surname or given else chars
        if not content or len(content) > 25:
            raise ValueError('A name chop needs 1–25 characters in --chars or --surname / --given.')
        if surname or given:
            columns = [list(s) for s in (surname, given) if s]
        elif len(chars) <= 4:
            split = 1 if len(chars) < 4 else 2
            columns = [list(s) for s in (chars[:split], chars[split:]) if s]
        else:
            rows = math.ceil(math.sqrt(len(chars)))
            columns = [list(chars[i:i + rows]) for i in range(0, len(chars), rows)]
        corner, weight = float(p['corner_radius']), int(p['weight'])
        if not 0 <= corner <= 30 or not 100 <= weight <= 900:
            raise ValueError('Use a corner radius of 0–30 and font weight of 100–900.')
        profile = default_resolver.resolve(str(p['zh_font']))
        ink = colors_mod.parse(str(p['color']))
        max_rows = max(map(len, columns))
        width, height = 124 / len(columns), 124 / max_rows
        nodes, sizes = [], []
        for col, letters in enumerate(columns):
            x = 18 + (len(columns) - col - 1) * width
            for row, letter in enumerate(letters):
                y = 18 + (max_rows - len(letters)) * height / 2 + row * height
                el, size = fitted_text(letter, [profile], (x + 3, y + 3, width - 6, height - 6),
                                       size=min(width, height), minimum=10,
                                       color='white' if p['inverted'] else ink, align='center')
                nodes.append(el)
                sizes.append(size)
        frame = (f'<rect x="9" y="9" width="142" height="142" '
                 f'rx="{svg.num(corner)}" fill="{ink if p["inverted"] else "none"}" '
                 f'stroke="{ink}" stroke-width="6"/>')
        view = (0., 0., 160., 160.)
        normalized = {**p, 'chars': chars, 'surname': surname, 'given': given,
                      'layout_chars': content, 'columns': [''.join(c) for c in columns],
                      'color': ink, 'zh_font': profile.family, 'char_count': len(content),
                      'glyph_font_size': min(sizes)}
        return StyleResult(svg=svg.svg_root(width=160, height=160, view_box_tuple=view) + frame + ''.join(nodes) + '</svg>',
                           normalized_params=normalized, warnings=[], fonts_used=[profile], view_box=view,
                           painted_bbox=(6., 6., 148., 148.), canonical_size_mm=(20., 20.),
                           style_id=self.META.id, style_version='3')


STYLE = _NameChop()

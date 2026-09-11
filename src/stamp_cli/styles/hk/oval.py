"""Hong Kong oval company seal.

Fixed proportions and measured lettering; all sizes are fitted to bounded areas.
"""
from ..base import ParamSpec, StyleMeta, StyleResult
from ...core.seal_layout import company_seal, rectangular_seal, RECT_PRESETS

_DEFAULT_STAR = "❋"
_DEFAULT_PRC_STAR_MM = 14.0
_DEFAULT_EN_FS = 46
_PRESET_IDS = list(RECT_PRESETS)

class _HkOval:
    META = StyleMeta(
        id="hk.oval",
        country="hk",
        shape="oval",
        title="Hong Kong company oval seal",
        description=(
            "Elliptical HK company chop: double border, inner ellipse, English "
            "name curved along the top, one or two centered Chinese lines, and a "
            "❋ floret at the bottom. buildOvalSvg."
        ),
        canonical_size_mm=(45.0, 30.0),
        reference="Measured business-stamp layout",
    )

    PARAMS = [
        ParamSpec(
            name="en", type=str, default="", required=True,
            help="English company name, curved along the top arc.",
        ),
        ParamSpec(
            name="zh_line1", type=str, default="",
            help="First (upper) centered Chinese line. Manual split — not "
                 "auto-derived from a single string.",
        ),
        ParamSpec(
            name="zh_line2", type=str, default="",
            help="Second (lower) centered Chinese line, e.g. (香港)有限公司.",
        ),
        ParamSpec(
            name="star", type=bool, default=True,
            help="Show the bottom floret/mark (the ❋ by default).",
        ),
        ParamSpec(
            name="star_glyph", type=str, default=_DEFAULT_STAR,
            help="Bottom mark glyph when --star is set (default ❋ U+274B).",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, blue, purple, black, vermilion…) or "
                 "#RRGGBB. Red is #FF0000.",
        ),
        ParamSpec(
            name="weight", type=int, default=700,
            help="Font weight for English + Chinese (100–900; "
                 "default 700).",
        ),
        ParamSpec(
            name="en_font", type=str, default="symbols",
            help="Font alias for the English + floret text (default Noto Sans "
                 "Symbols).",
        ),
        ParamSpec(
            name="zh_font", type=str, default="song",
            help="Font alias for the Chinese text (default Songti SC).",
        ),
    ]

    DEFAULTS = {
        "en": "",
        "zh_line1": "",
        "zh_line2": "",
        "star": True,
        "star_glyph": _DEFAULT_STAR,
        "color": "red",
        "weight": 700,
        "en_font": "symbols",
        "zh_font": "song",
    }

    def build_svg(self, **params) -> StyleResult:
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        return company_seal(self, p, oval=True)


STYLE = _HkOval()

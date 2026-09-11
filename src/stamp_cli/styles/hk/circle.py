"""Hong Kong circular company seal.

Fixed proportions and measured lettering; all sizes are fitted to bounded areas.
"""
from ..base import ParamSpec, StyleMeta, StyleResult
from ...core.seal_layout import company_seal, rectangular_seal, RECT_PRESETS

_DEFAULT_STAR = "❋"
_DEFAULT_PRC_STAR_MM = 14.0
_DEFAULT_EN_FS = 46
_PRESET_IDS = list(RECT_PRESETS)

class _HkCircle:
    META = StyleMeta(
        id="hk.circle",
        country="hk",
        shape="circle",
        title="Hong Kong round company seal",
        description=(
            "Round company chop: three concentric border rings, English name "
            "curved along the top, one or two centered Chinese lines, and a ❋ "
            "floret (or English text) along the bottom. Optional real "
            "five-pointed star for a PRC-style centre. "
            ""
        ),
        canonical_size_mm=(42.0, 42.0),
        reference="Measured business-stamp layout",
    )

    PARAMS = [
        ParamSpec(
            name="en", type=str, default="",
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
            name="en_bottom", type=str, default="",
            help="English text curved along the BOTTOM arc. Overrides the "
                 "default ❋ floret when set.",
        ),
        ParamSpec(
            name="star", type=bool, default=True,
            help="Show the bottom floret/mark (the ❋ by default) when --en-bottom "
                 "is empty.",
        ),
        ParamSpec(
            name="star_glyph", type=str, default=_DEFAULT_STAR,
            help="Bottom mark glyph when --star is set (default ❋ U+274B).",
        ),
        ParamSpec(
            name="prc_star", type=bool, default=False,
            help="Render a real five-pointed red <polygon> star at the centre "
                 "(PRC mainland official-seal motif).",
        ),
        ParamSpec(
            name="prc_star_size", type=float, default=_DEFAULT_PRC_STAR_MM,
            help="PRC centre-star height in mm (point-to-point). Default 14mm "
                 "per the mainland 42mm-seal spec.",
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
            name="font_size", type=int, default=_DEFAULT_EN_FS,
            help="Maximum English arc font size "
                 "(default 46).",
        ),
        ParamSpec(
            name="en_font", type=str, default="sans",
            help="Font alias for the English text (default a system sans-serif; "
                 "symbol font resolved separately).",
        ),
        ParamSpec(
            name="zh_font", type=str, default="song",
            help="Font alias for the Chinese text (default Songti SC).",
        ),
        ParamSpec(
            name="en_size", type=int, default=0,
            help="Override English font size (0 = auto from the "
                 "font metrics). Ring/arc geometry stays fixed, so this scales "
                 "the top-arc text.",
        ),
        ParamSpec(
            name="en_spacing", type=float, default=None,
            help="Override English letter-spacing in viewBox units "
                 "(unset = 0; the name scales down for "
                 "long names).",
        ),
        ParamSpec(
            name="zh_size", type=int, default=0,
            help="Force BOTH Chinese lines to this font size (0 = auto per "
                 "line). Use to make the two lines the same size.",
        ),
    ]

    DEFAULTS = {
        "en": "",
        "zh_line1": "",
        "zh_line2": "",
        "en_bottom": "",
        "star": True,
        "star_glyph": _DEFAULT_STAR,
        "prc_star": False,
        "prc_star_size": _DEFAULT_PRC_STAR_MM,
        "color": "red",
        "weight": 700,
        "font_size": _DEFAULT_EN_FS,
        "en_font": "sans",
        "zh_font": "song",
        "en_size": 0,
        "en_spacing": None,
        "zh_size": 0,
    }

    def build_svg(self, **params) -> StyleResult:
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        return company_seal(self, p, oval=False)


STYLE = _HkCircle()

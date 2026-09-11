"""Hong Kong rectangular business stamp.

Fixed proportions and measured lettering; all sizes are fitted to bounded areas.
"""
from ..base import ParamSpec, StyleMeta, StyleResult
from ...core.seal_layout import company_seal, rectangular_seal, RECT_PRESETS

_DEFAULT_STAR = "❋"
_DEFAULT_PRC_STAR_MM = 14.0
_DEFAULT_EN_FS = 46
_PRESET_IDS = list(RECT_PRESETS)

class _HkRect:
    META = StyleMeta(
        id="hk.rect",
        country="hk",
        shape="rect",
        title="Hong Kong rectangular company / signature stamp",
        description=(
            "Landscape rubber stamp: English company name, Chinese name, an "
            "optional dashed signature line and 'For and on behalf of' / "
            "'Authorized Signature(s)' captions. Presets: sign, address, "
            "cheque, certified-true-copy. "
        ),
        canonical_size_mm=(60.0, 60.0 * 120 / 260),
        reference="Measured business-stamp layout",
    )

    PARAMS = [
        ParamSpec(
            name="preset", type=str, default="sign", enum=_PRESET_IDS,
            help="Layout preset — seeds line1/line2/signature defaults that any "
                 "explicit flag overrides. One of: " + ", ".join(_PRESET_IDS) + ".",
        ),
        ParamSpec(
            name="line1", type=str, default=None,
            help="Top line (English company name). Overrides the preset.",
        ),
        ParamSpec(
            name="line2", type=str, default=None,
            help="Second line (Chinese name, or address). Overrides the preset. "
                 "Use \\n in the value for a multi-line address.",
        ),
        ParamSpec(
            name="signature_top", type=str, default=None,
            help="Top-left italic caption (default 'For and on behalf of' for "
                 "the sign preset). Overrides the preset; defaults are used when "
                 "left unset.",
        ),
        ParamSpec(
            name="signature_bottom", type=str, default=None,
            help="Lower italic caption (default 'Authorized Signature(s)' for "
                 "the sign preset). Embed \\n for a centered multi-line block.",
        ),
        ParamSpec(
            name="signature_line", type=bool, default=None,
            help="Show the dashed signature line (sign preset only by "
                 "default).",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, blue, purple, black, vermilion…) or "
                 "#RRGGBB. Red is #FF0000.",
        ),
        ParamSpec(
            name="weight", type=int, default=700,
            help="Font weight for both name lines (the "
                 "cheque preset uses 700).",
        ),
        ParamSpec(
            name="en_font", type=str, default="times",
            help="Font alias for the English line + signature captions "
                 "(default Times New Roman).",
        ),
        ParamSpec(
            name="zh_font", type=str, default="song",
            help="Font alias for the Chinese line (default Songti SC).",
        ),
    ]

    DEFAULTS = {
        "preset": "sign",
        "line1": None,
        "line2": None,
        "signature_top": None,
        "signature_bottom": None,
        "signature_line": None,
        "color": "red",
        "weight": 700,
        "en_font": "times",
        "zh_font": "song",
    }

    def build_svg(self, **params) -> StyleResult:
        return rectangular_seal(self, params)


STYLE = _HkRect()

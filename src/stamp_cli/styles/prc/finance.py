"""``prc.finance`` — PRC finance special seal (财务专用章).

A 财务专用章 is, by regulation and in practice, a **department/special-purpose
round seal whose purpose label is fixed to 财务专用章**. Rather than re-implement
(and re-bug) the round-seal geometry, this style **delegates to
``prc.department_round``** with the purpose pinned — so it inherits the correct
single 1 mm border, the ~⅓-diameter centred star, and the radial (upright,
feet-inward) CJK name placement automatically. Only the style id, title and the
fixed label differ.

This replaced an earlier standalone implementation that the build verify flagged
for a too-small star (~16 % vs the ~33 % spec) and an unrequested double border.
"""

from __future__ import annotations

import dataclasses

from ..base import ParamSpec, StyleMeta, StyleResult
from .department_round import STYLE as _DEPT

_VERSION = "2"
_DEFAULT_LABEL = "财务专用章"


class _PrcFinance:
    META = StyleMeta(
        id="prc.finance",
        country="prc",
        shape="circle",
        title="PRC finance special seal (财务专用章)",
        description=(
            "Mainland 财务专用章: a 38 mm round department seal with the purpose "
            "fixed to 财务专用章 — company name radial along the top arc, central "
            "five-pointed star, the label below centre. Red, Songti. Delegates to "
            "prc.department_round so border/star/text fidelity stays consistent."
        ),
        canonical_size_mm=(38.0, 38.0),
        reference="国发〔1999〕25号; delegates to prc.department_round",
    )

    PARAMS = [
        ParamSpec(
            name="company", type=str, default="", required=True,
            help="Company name (Chinese), curved along the top arc.",
        ),
        ParamSpec(
            name="label", type=str, default=_DEFAULT_LABEL,
            help="Horizontal centre label (default 财务专用章).",
        ),
        ParamSpec(
            name="star", type=bool, default=True,
            help="Show the central five-pointed star.",
        ),
        ParamSpec(
            name="color", type=str, default="red",
            help="Ink color: preset (red, vermilion…) or #RRGGBB (PRC red #FF0000).",
        ),
        ParamSpec(
            name="weight", type=int, default=600,
            help="Font weight for the Chinese text.",
        ),
        ParamSpec(
            name="font", type=str, default="song",
            help="Font alias for the Chinese text (default Songti SC, 简化宋体).",
        ),
    ]

    DEFAULTS = {
        "company": "",
        "label": _DEFAULT_LABEL,
        "star": True,
        "color": "red",
        "weight": 600,
        "font": "song",
    }

    def build_svg(self, **params) -> StyleResult:
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        company = str(p["company"]).strip()
        if not company:
            raise ValueError("prc.finance requires --company (the Chinese name).")
        label = str(p["label"]).strip() or _DEFAULT_LABEL

        result = _DEPT.build_svg(
            company=company,
            purpose=label,
            star=bool(p["star"]),
            color=p["color"],
            weight=p["weight"],
            font=p["font"],
        )
        # Re-stamp identity so the result reports as prc.finance, not the
        # delegate. StyleResult is frozen — use dataclasses.replace.
        return dataclasses.replace(
            result, style_id="prc.finance", style_version=_VERSION
        )


STYLE = _PrcFinance()

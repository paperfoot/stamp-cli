"""The style contract — the only abstraction in the system.

Every stamp style is a pure function ``params -> StyleResult`` (an SVG string
plus metadata). Click options, JSON schema, ``agent-info``, validation and help
are ALL derived from a style's :data:`PARAMS` list, so adding a style never
means touching the CLI.

These four dataclasses / the protocol are defined EXACTLY per PLAN.md §7. Do not
drift from them — downstream style authors import these names and the registry,
manifest, and CLI all destructure them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..core.fonts import FontProfile


@dataclass(frozen=True)
class StyleMeta:
    """Static identity + provenance of a style."""

    id: str
    country: str
    shape: str
    title: str
    description: str
    canonical_size_mm: tuple[float, float] | None
    reference: str  # cite the algorithm source (STAMP4U, SealUtil, MOJ reg, …)


@dataclass(frozen=True)
class ParamSpec:
    """A neutral parameter description — NOT a Click option.

    The CLI builds a Click option from this; the manifest builds a JSON-schema
    entry from this; validation checks ``required``/``enum`` against this.
    """

    name: str
    type: type
    default: Any
    help: str
    required: bool = False
    enum: list | None = None


@dataclass(frozen=True)
class StyleResult:
    """What :meth:`StyleSpec.build_svg` returns — never a bare string.

    Carries the SVG plus everything callers need to rasterize deterministically
    and to report what was produced (fonts pinned, the viewBox to scale, the
    painted bounding box, warnings surfaced during normalization).
    """

    svg: str
    normalized_params: dict
    warnings: list[str]
    fonts_used: list[FontProfile]
    view_box: tuple[float, float, float, float]
    painted_bbox: tuple[float, float, float, float]
    canonical_size_mm: tuple[float, float] | None
    style_id: str
    style_version: str


@runtime_checkable
class StyleSpec(Protocol):
    """Structural protocol every style module's ``STYLE`` object satisfies."""

    META: StyleMeta
    PARAMS: list[ParamSpec]
    DEFAULTS: dict

    def build_svg(self, **params: Any) -> StyleResult: ...


__all__ = [
    "StyleMeta",
    "ParamSpec",
    "StyleResult",
    "StyleSpec",
    "FontProfile",
    "field",
]

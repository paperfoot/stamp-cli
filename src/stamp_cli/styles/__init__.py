"""Resilient auto-discovery style registry.

A style is added to the system simply by dropping a module under this package
(``hk/``, ``prc/``, ``personal/``, ``western/`` or the package root) that exposes
a module-level ``STYLE`` object satisfying
:class:`~stamp_cli.styles.base.StyleSpec`. **No edit to this file is required** —
which is the whole point: parallel authors never collide here.

Discovery is *resilient*: every submodule is imported inside its own
try/except. One broken style records a load error and is skipped; it never
prevents the others (or the CLI itself) from working. Collected errors surface
in ``stamp doctor``.

Public API:
    REGISTRY      -> dict[str, StyleSpec]      (id -> style)
    get(id)       -> StyleSpec | None
    all()         -> list[StyleSpec]           (sorted by id)
    load_errors() -> list[LoadError]
    reload()      -> re-run discovery (mainly for tests)
"""

from __future__ import annotations

import importlib
import pkgutil
import traceback
from dataclasses import dataclass

from .base import ParamSpec, StyleMeta, StyleResult, StyleSpec  # re-export

__all__ = [
    "REGISTRY",
    "get",
    "all",
    "load_errors",
    "reload",
    "LoadError",
    "StyleMeta",
    "ParamSpec",
    "StyleResult",
    "StyleSpec",
]


@dataclass(frozen=True)
class LoadError:
    """A style module that failed to import or register cleanly."""

    module: str
    error: str
    traceback: str


REGISTRY: dict[str, StyleSpec] = {}
_LOAD_ERRORS: list[LoadError] = []

# Submodules that are infrastructure, not styles — never imported as styles.
_SKIP = {"base", "__init__"}


def _register_module(module_name: str) -> None:
    """Import one module and register its ``STYLE`` if present.

    Failures are caught and recorded; they never propagate.
    """
    try:
        mod = importlib.import_module(module_name)
    except Exception as e:  # import-time error in a style module
        _LOAD_ERRORS.append(
            LoadError(module=module_name, error=f"{type(e).__name__}: {e}",
                      traceback=traceback.format_exc())
        )
        return

    style = getattr(mod, "STYLE", None)
    if style is None:
        # Not every module is a style (helpers, presets). Silently ignore.
        return

    try:
        meta = style.META
        style_id = meta.id
    except Exception as e:
        _LOAD_ERRORS.append(
            LoadError(module=module_name,
                      error=f"STYLE present but invalid: {type(e).__name__}: {e}",
                      traceback=traceback.format_exc())
        )
        return

    if style_id in REGISTRY:
        _LOAD_ERRORS.append(
            LoadError(module=module_name,
                      error=f"duplicate style id '{style_id}' "
                            f"(already provided by another module)",
                      traceback="")
        )
        return

    REGISTRY[style_id] = style


def _discover() -> None:
    """Walk this package recursively and register every style module."""
    REGISTRY.clear()
    _LOAD_ERRORS.clear()
    package = __name__  # 'stamp_cli.styles'
    pkg = importlib.import_module(package)
    for mod_info in pkgutil.walk_packages(pkg.__path__, prefix=package + "."):
        leaf = mod_info.name.rsplit(".", 1)[-1]
        if leaf in _SKIP or leaf.startswith("_"):
            continue
        if mod_info.ispkg:
            # Sub-package (hk/, prc/ …): its modules are walked too; skip the
            # package's own __init__ as a style source.
            continue
        _register_module(mod_info.name)


def get(style_id: str) -> StyleSpec | None:
    """Return the style with ``style_id`` or ``None``."""
    return REGISTRY.get(style_id)


def all() -> list[StyleSpec]:  # noqa: A001 - intentional public name
    """Return all registered styles, sorted by id."""
    return [REGISTRY[k] for k in sorted(REGISTRY)]


def load_errors() -> list[LoadError]:
    """Return the list of style modules that failed to load."""
    return list(_LOAD_ERRORS)


def reload() -> None:
    """Re-run discovery (used by tests after adding/removing style modules)."""
    _discover()


# Discover on import. Wrapped so a catastrophic discovery failure (e.g. the
# package itself is unimportable) still leaves an empty, usable registry.
try:
    _discover()
except Exception as e:  # pragma: no cover - defensive
    _LOAD_ERRORS.append(
        LoadError(module=__name__, error=f"discovery failed: {e}",
                  traceback=traceback.format_exc())
    )

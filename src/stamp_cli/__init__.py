"""stamp-cli — generate company stamps / seals / chops as SVG (+ derived PNG).

Each style is a pure function ``params -> SVG``; PNG is rasterized from that SVG
via resvg. The CLI surface (nested groups + the machine-first ``generate``
entry) is built dynamically from the auto-discovered style registry.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from ._version import __version__

__all__ = ["__version__", "cli"]


def __getattr__(name: str) -> Any:
    """Load the Click entry point only when callers request it."""
    if name == "cli":
        command = import_module(".cli", __name__).cli
        globals()[name] = command
        return command
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

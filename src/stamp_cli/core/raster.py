"""SVG → PNG rasterization via ``resvg_py``.

This is a thin, faithful wrapper around ``resvg_py.svg_to_bytes`` — the exact
call the proof spike (``spike/render_oval.py``) validated. resvg has its own Rust
text stack (no Cairo, no system HarfBuzz) and is reproducible across OS/arch,
which is what makes our golden RGBA-hash tests possible.

Design notes:
  * We pass an explicit ``font_files`` list. For production rendering callers
    also pass ``skip_system_fonts=True`` so output depends only on pinned fonts.
  * ``background='transparent'`` means *omit* the background entirely (resvg
    leaves the canvas transparent when ``background`` is ``None``). Any other
    value is forwarded as a CSS color (``'white'``, ``'#FF0000'`` …).
  * ``resvg_py`` missing or broken raises :class:`RasterizerMissingError`, which
    the CLI maps to exit code 3.
"""

from __future__ import annotations


class RasterizerMissingError(RuntimeError):
    """Raised when ``resvg_py`` cannot be imported or invoked.

    The CLI maps this to exit code 3 (rasterizer missing).
    """


def _import_resvg():
    try:
        import resvg_py  # type: ignore
    except Exception as e:  # ImportError, or a broken native extension
        raise RasterizerMissingError(
            "resvg_py is not available. Install it with `uv add resvg-py` "
            f"(it is the SVG rasterizer this tool depends on). Import error: {e}"
        ) from e
    return resvg_py


def resvg_version() -> str:
    """Return the underlying resvg engine version (for ``doctor``)."""
    resvg_py = _import_resvg()
    return getattr(resvg_py, "__resvg_version__", "unknown")


def binding_version() -> str:
    """Return the ``resvg_py`` Python binding version (for ``doctor``)."""
    resvg_py = _import_resvg()
    return getattr(resvg_py, "__version__", "unknown")


def render_png(
    svg: str,
    *,
    font_files: list[str],
    width: int | None = None,
    dpi: int | None = None,
    background: str = "transparent",
    skip_system_fonts: bool = False,
) -> bytes:
    """Rasterize an SVG string to PNG bytes.

    Args:
        svg: The complete SVG document as a string.
        font_files: Absolute paths to font files made available to resvg. These
            are the pinned fonts the SVG's ``font-family`` names resolve against.
        width: Output width in pixels. The height follows from the viewBox aspect
            ratio. ``None`` lets resvg use the SVG's intrinsic size.
        dpi: Rendering DPI. ``None`` uses the resvg default. Mutually useful with
            a physical-size SVG; ``width`` takes precedence for on-screen scale.
        background: ``'transparent'`` (default) omits any background, leaving an
            alpha channel. Any other value (``'white'``, ``'#RRGGBB'``, a CSS
            color name) is forwarded to resvg as the canvas background.
        skip_system_fonts: When ``True``, resvg uses *only* ``font_files`` and
            ignores host-installed fonts — required for deterministic output.

    Returns:
        PNG-encoded bytes.

    Raises:
        RasterizerMissingError: if ``resvg_py`` is unavailable.
    """
    resvg_py = _import_resvg()

    bg = None if background in (None, "transparent", "none", "alpha") else background

    kwargs: dict = {
        "svg_string": svg,
        "font_files": list(font_files),
        "skip_system_fonts": skip_system_fonts,
        # resvg-py's binding defaults to 0 DPI, which makes physical units invalid.
        "dpi": 96.0 if dpi is None else float(dpi),
    }
    if background is not None:
        # Pass None for transparent (omit bg), else the CSS color string.
        kwargs["background"] = bg
    if width is not None:
        kwargs["width"] = int(width)

    try:
        return bytes(resvg_py.svg_to_bytes(**kwargs))
    except RasterizerMissingError:
        raise
    except Exception as e:
        # A render-time failure (bad SVG, font issue inside resvg). Surface as a
        # rasterizer problem so the CLI returns a meaningful exit code rather
        # than a bare traceback.
        raise RasterizerMissingError(f"resvg failed to rasterize the SVG: {e}") from e

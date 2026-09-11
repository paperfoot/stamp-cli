"""stamp — agent-friendly CLI for generating company stamps / seals / chops.

The command tree is built *dynamically* from the style registry
(:mod:`stamp_cli.styles`):

  * Nested groups for humans — ``stamp hk oval``, ``stamp prc state-owned-round``
    — with one Click option per :class:`~stamp_cli.styles.base.ParamSpec`.
  * A machine-first entry — ``stamp generate --style <id> --params <json|->`` —
    whose stable id survives refactors.

Plus introspection: ``agent-info``, ``doctor``, ``validate``, ``list``,
``fonts``, ``colors``. Every command honors the shared output flags and returns
a semantic exit code (see :mod:`stamp_cli.core.output`).

Adding a style never requires editing this file: the groups, options, help and
schema are all derived from ``PARAMS``.
"""

from __future__ import annotations

import json
import re
import sys
from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path
from typing import Any

import click

from . import manifest, styles
from .core import colors as colors_mod
from .core import fonts as fonts_mod
from .core import output as out_mod
from .core import raster as raster_mod
from .core import export as export_mod
from .core import provenance
from .core.validation import validate_params
from .core.fonts import FontMissingError
from .core.output import (
    EXIT_FONT_MISSING,
    EXIT_OK,
    EXIT_RASTERIZER_MISSING,
    EXIT_USER_ERROR,
    StampError,
)
from .core.raster import RasterizerMissingError

VERSION = manifest.VERSION
_BINARY_STDOUT = ContextVar("stamp_binary_stdout", default=False)


# ──────────────────────────────────────────────────────────────────────────────
# Shared output flags
# ──────────────────────────────────────────────────────────────────────────────
def shared_output_options(f):
    """Decorator applying the output / styling flags shared by every render command.

    Note: ink ``--color`` is intentionally **not** here — it is a per-style
    :class:`~stamp_cli.styles.base.ParamSpec` (styles own their fill), so the CLI
    generates ``--color`` from each style's ``PARAMS``. Declaring it both here and
    there made Click warn about a duplicate option and bind ambiguously.
    """
    f = click.option("--bg", "--background", "bg", default="transparent",
                     show_default=True,
                     help="Background: transparent | white | <preset> | #RRGGBB.")(f)
    f = click.option("--size", "--px-width", "size", default=None, type=click.IntRange(16, 8192),
                     help="PNG width in pixels; alternative to --dpi.")(f)
    f = click.option("--dpi", default=None, type=click.IntRange(36, 2400),
                     help="PNG print resolution (default: 300 DPI).")(f)
    f = click.option("--width-mm", default=None, type=click.FloatRange(5, 300),
                     help="Printed width in millimetres; preserves the style's proportions.")(f)
    f = click.option("--output", "-o", default=None,
                     type=click.Path(dir_okay=False),
                     help="Destination path. Extension picks the format "
                          "(.svg/.png); no extension -> both.")(f)
    f = click.option("--format", "fmt",
                     type=click.Choice(["svg", "png", "both"]), default=None,
                     help="Force output format. Overrides path extension.")(f)
    f = click.option("--stdout", is_flag=True,
                     help="Write a single artifact's bytes to stdout.")(f)
    f = click.option("--json", "json_out", is_flag=True,
                     help="Emit a JSON result envelope.")(f)
    f = click.option("--force", is_flag=True, help="Replace existing output files.")(f)
    f = click.option("--open", "open_result", is_flag=True, help="Open the saved result in your default viewer.")(f)
    f = click.option("--weathered", is_flag=True,
                     help="Add subtle ink wear, consistently in SVG and PNG.")(f)
    f = click.option("--seed", default=None, type=int,
                     help="Reproducible weathering seed.")(f)
    return f


# Keys consumed by the output/styling layer — everything else is a style param.
# (``color`` is a per-style param, not shared; see ``shared_output_options``.)
_SHARED_KEYS = {
    "bg", "size", "dpi", "output", "fmt",
    "stdout", "json_out", "weathered", "seed", "width_mm", "force", "open_result",
}


# ──────────────────────────────────────────────────────────────────────────────
# The shared render pipeline (one place; nested + generate both call it)
# ──────────────────────────────────────────────────────────────────────────────
def _run_style(spec, style_params: dict, shared: dict) -> int:
    """Build SVG for ``spec`` with ``style_params`` and write per ``shared`` flags.

    Returns a semantic exit code. Translates the three failure classes
    (user / font / rasterizer) into their codes.
    """
    style_id = spec.META.id

    # Reject unusable destinations and mistyped parameters before expensive work.
    try:
        out_mod.output_paths(shared["output"], shared["fmt"], shared["stdout"],
                             force=shared["force"], open_result=shared["open_result"])
        if shared["size"] is not None and shared["dpi"] is not None:
            raise ValueError("Choose --size or --dpi, not both.")
        if shared["seed"] is not None and not shared["weathered"]:
            raise ValueError("--seed requires --weathered.")
        validate_params(spec, style_params)
        result = spec.build_svg(**style_params)
        width_mm, height_mm, pixel_width, actual_dpi = export_mod.dimensions(
            result, width_mm=shared["width_mm"], size=shared["size"], dpi=shared["dpi"])
    except StampError as e:
        return _fail(str(e), e.exit_code, style_id, shared["json_out"])
    except FontMissingError as e:
        return _fail(str(e), EXIT_FONT_MISSING, style_id, shared["json_out"])
    except (ValueError, KeyError, TypeError) as e:
        return _fail(str(e), EXIT_USER_ERROR, style_id, shared["json_out"])

    # 2. Resolve background to a CSS value / 'transparent'.
    bg = shared["bg"]
    if bg not in ("transparent", "none", "white"):
        try:
            bg = colors_mod.parse(bg)
        except ValueError as e:
            return _fail(str(e), EXIT_USER_ERROR, style_id, shared["json_out"])

    font_files = [fp.file_path for fp in result.fonts_used]
    source = export_mod.prepare_svg(result, width_mm=width_mm, height_mm=height_mm,
                                    background=bg, weathered=shared["weathered"],
                                    seed=shared["seed"] or 0)
    reference = result.normalized_params.get("sig_id")
    metadata = provenance.record(style_id, reference)
    source = provenance.embed_svg(source, metadata)

    # 3. PNG is produced lazily so svg-only runs never touch resvg.
    def png_provider() -> bytes:
        return export_mod.with_resolution(raster_mod.render_png(
            source,
            font_files=font_files,
            width=pixel_width,
            background=bg,
            skip_system_fonts=True,
        ), actual_dpi, metadata)

    extra = {
        "warnings": result.warnings,
        "fonts": [fp.family for fp in result.fonts_used],
        "view_box": list(result.view_box),
        "canonical_size_mm": (
            list(result.canonical_size_mm) if result.canonical_size_mm else None
        ),
        "normalized_params": result.normalized_params,
        "style_version": result.style_version,
        "reference": reference,
        "size_mm": [width_mm, height_mm],
        "weathered": bool(shared["weathered"]),
        "seed": (shared["seed"] or 0) if shared["weathered"] else None,
    }

    try:
        return out_mod.write_result(
            svg=source,
            png_bytes_provider=png_provider,
            style_id=style_id,
            output=shared["output"],
            fmt=shared["fmt"],
            stdout=shared["stdout"],
            json_out=shared["json_out"],
            background=bg,
            width=pixel_width,
            dpi=actual_dpi,
            extra=extra,
            force=shared["force"],
            open_result=shared["open_result"],
        )
    except RasterizerMissingError as e:
        return _fail(str(e), EXIT_RASTERIZER_MISSING, style_id, shared["json_out"])
    except StampError as e:
        return _fail(str(e), e.exit_code, style_id, shared["json_out"])
    except OSError as e:
        return _fail(str(e), out_mod.EXIT_IO_ERROR, style_id, shared["json_out"])


def _fail(message: str, code: int, style: str | None, json_out: bool) -> int:
    """Emit an error (JSON envelope or stderr line) and return the exit code."""
    if json_out:
        out_mod.emit_json(out_mod.error_envelope(message, code=code, style=style),
                          stream=sys.stderr if _BINARY_STDOUT.get() else sys.stdout)
    else:
        click.echo(f"error: {message}", err=True)
    return code


def _split_params(all_params: dict) -> tuple[dict, dict]:
    """Split a Click params dict into (style_params, shared_flags)."""
    shared = {k: all_params.get(k) for k in _SHARED_KEYS}
    style_params = {k: v for k, v in all_params.items() if k not in _SHARED_KEYS}
    return style_params, shared


# ──────────────────────────────────────────────────────────────────────────────
# Dynamic option building from PARAMS
# ──────────────────────────────────────────────────────────────────────────────
def _click_type(param: "styles.ParamSpec"):
    if param.enum:
        return click.Choice([str(e) for e in param.enum])
    if param.type is bool:
        return None  # handled as a flag
    if param.type is int:
        return int
    if param.type is float:
        return float
    return str


def _option_name(param_name: str) -> str:
    """``zh_line1`` -> ``--zh-line1``."""
    return "--" + param_name.replace("_", "-")


def _make_style_command(spec, *, name=None, defaults=None):
    """Create a Click command implementing one style's nested invocation."""

    @shared_output_options
    def _impl(**all_params):
        style_params, shared = _split_params(all_params)
        code = _run_style(spec, style_params, shared)
        if code != EXIT_OK:
            raise SystemExit(code)

    # Attach a Click option for every ParamSpec (outermost-last ordering is fine).
    for param in reversed(spec.PARAMS):
        if defaults and param.name in defaults:
            param = replace(param, default=defaults[param.name])
        if name == "sign" and param.name == "name":
            param = replace(param, required=True)
        opt = _option_name(param.name)
        if param.type is bool:
            flag = f"{opt}/--no-{param.name.replace('_', '-')}"
            _impl = click.option(flag, param.name, default=bool(param.default),
                                 show_default=True, help=param.help)(_impl)
            continue
        if param.type is list:
            # Repeatable option: --lines A --lines B -> ('A', 'B'). Without
            # multiple=True a list param silently keeps only the last value.
            _impl = click.option(opt, param.name, multiple=True,
                                 help=param.help)(_impl)
            continue
        kwargs: dict[str, Any] = {"help": param.help, "required": bool(param.required)}
        ctype = _click_type(param)
        if ctype is not None:
            kwargs["type"] = ctype
        if not param.required:
            kwargs["default"] = param.default
            if param.default is not None:
                kwargs["show_default"] = True
        _impl = click.option(opt, param.name, **kwargs)(_impl)

    # Command name: last path segment of the id, dash-cased. hk.oval -> oval;
    # prc.state_owned_round -> state-owned-round.
    leaf = spec.META.id.split(".")[-1].replace("_", "-")
    _impl = click.command(name=name or leaf, help=(
        "Create a framed signature graphic from a name or scanned image.\n\n"
        "Example: stamp sign --name 'Alex Morgan' -o signature.png\n\n"
        "Use --layout clean for an understated name line, or signature-only for bare ink.\n"
        "The optional ID is a graphic fingerprint, not a digital certificate."
        if name == "sign" else _style_help(spec)))(_impl)
    return _impl


def _style_help(spec) -> str:
    meta = spec.META
    size = ""
    if meta.canonical_size_mm:
        size = f"  [{meta.canonical_size_mm[0]}×{meta.canonical_size_mm[1]}mm]"
    return f"{meta.title}{size}\n\n{meta.description}\n\nReference: {meta.reference}"


# ──────────────────────────────────────────────────────────────────────────────
# Root group, built dynamically
# ──────────────────────────────────────────────────────────────────────────────
class _LazyRoot(click.Group):
    """Give parsing errors the same JSON/exit-code contract as render errors."""

    def main(self, args=None, prog_name=None, complete_var=None, standalone_mode=True, **extra):
        argv = list(sys.argv[1:] if args is None else args)
        token = _BINARY_STDOUT.set("--stdout" in argv)
        try:
            try:
                return super().main(args=argv, prog_name=prog_name, complete_var=complete_var,
                                    standalone_mode=False, **extra)
            except click.ClickException as e:
                code = _fail(e.format_message(), EXIT_USER_ERROR, None, "--json" in argv)
                if standalone_mode:
                    raise SystemExit(code) from e
                raise
        finally:
            _BINARY_STDOUT.reset(token)


@click.group(cls=_LazyRoot, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(VERSION, prog_name="stamp")
def cli() -> None:
    """Signature graphics, company seals and office stamps. SVG + print-ready PNG.

    \b
    Start:    stamp sign --name "Alex Morgan" -o signature.png
              stamp preview --open             (browse every style)
              stamp list signature             (search the catalog)
    Agents:   stamp generate --style hk.oval --params params.json -o seal
              stamp agent-info --json        (full machine manifest)

    The style catalog is discovered at runtime; `stamp list` shows what's loaded.
    """


def _build_nested_groups() -> None:
    """Group styles by country prefix and attach as subgroups of ``cli``.

    ``hk.oval`` -> group ``hk`` / command ``oval``. The country segment is the id
    prefix before the first dot. Personal/western use their own prefix.
    """
    groups: dict[str, click.Group] = {}
    for spec in styles.all():
        parts = spec.META.id.split(".", 1)
        prefix = parts[0] if len(parts) == 2 else "misc"
        if prefix not in groups:
            grp = click.Group(name=prefix, help=f"{prefix} styles.")
            groups[prefix] = grp
            cli.add_command(grp)
        groups[prefix].add_command(_make_style_command(spec))
    signature = styles.get("esign.signature")
    if signature:
        cli.add_command(_make_style_command(signature, name="sign", defaults={
            "signature": "typed", "layout": "classic", "show_id": True,
            "font": "sans",
        }))


# ──────────────────────────────────────────────────────────────────────────────
# generate — machine-first entry
# ──────────────────────────────────────────────────────────────────────────────
@cli.command(name="generate")
@click.option("--style", "style_id", required=True, help="Style id (see `stamp list`).")
@click.option("--params", "params_src", default=None,
              help="Path to a JSON params file, or '-' to read JSON from stdin.")
@click.option("--params-stdin", is_flag=True, help="Read JSON params from stdin.")
@shared_output_options
def generate(style_id, params_src, params_stdin, **shared_raw):
    """Render any style by id from JSON params (machine-first entry).

    Examples:

    \b
        stamp generate --style hk.oval --params params.json -o out
        echo '{"en":"..."}' | stamp generate --style hk.oval --params - -o seal
    """
    spec = styles.get(style_id)
    if spec is None:
        known = ", ".join(sorted(styles.REGISTRY)) or "(none loaded)"
        code = _fail(f"unknown style '{style_id}'. Known: {known}",
                     EXIT_USER_ERROR, style_id, shared_raw.get("json_out", False))
        raise SystemExit(code)

    # Load params JSON.
    raw = "{}"
    try:
        if params_stdin and params_src:
            raise ValueError("Choose --params or --params-stdin, not both.")
        if params_stdin or params_src == "-":
            raw = sys.stdin.read()
        elif params_src:
            with open(params_src, encoding="utf-8") as fp:
                raw = fp.read()
    except (OSError, UnicodeError, ValueError) as e:
        code = _fail(f"cannot read params: {e}", out_mod.EXIT_IO_ERROR if isinstance(e, OSError) else EXIT_USER_ERROR, style_id,
                     shared_raw.get("json_out", False))
        raise SystemExit(code)

    try:
        params = json.loads(raw) if raw.strip() else {}
        if not isinstance(params, dict):
            raise ValueError("params JSON must be an object")
    except (ValueError, json.JSONDecodeError) as e:
        code = _fail(f"invalid params JSON: {e}", EXIT_USER_ERROR, style_id,
                     shared_raw.get("json_out", False))
        raise SystemExit(code)

    _, shared = _split_params({**shared_raw})
    code = _run_style(spec, params, shared)
    if code != EXIT_OK:
        raise SystemExit(code)


# ──────────────────────────────────────────────────────────────────────────────
# validate — dry run
# ──────────────────────────────────────────────────────────────────────────────
@cli.command(name="validate")
@click.option("--style", "style_id", required=True, help="Style id.")
@click.option("--params", "params_src", default=None,
              help="JSON params file, or '-' for stdin.")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON.")
def validate(style_id, params_src, json_out):
    """Dry-run a style: normalize params, resolve fonts, report size. No render."""
    spec = styles.get(style_id)
    if spec is None:
        known = ", ".join(sorted(styles.REGISTRY)) or "(none loaded)"
        raise SystemExit(_fail(f"unknown style '{style_id}'. Known: {known}",
                               EXIT_USER_ERROR, style_id, json_out))

    raw = "{}"
    try:
        if params_src == "-":
            raw = sys.stdin.read()
        elif params_src:
            with open(params_src, encoding="utf-8") as fp:
                raw = fp.read()
        params = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError) as e:
        raise SystemExit(_fail(f"cannot read params: {e}", out_mod.EXIT_IO_ERROR if isinstance(e, OSError) else EXIT_USER_ERROR,
                               style_id, json_out))

    try:
        validate_params(spec, params)
        result = spec.build_svg(**params)
    except FontMissingError as e:
        raise SystemExit(_fail(str(e), EXIT_FONT_MISSING, style_id, json_out))
    except (ValueError, KeyError, TypeError) as e:
        raise SystemExit(_fail(str(e), EXIT_USER_ERROR, style_id, json_out))

    report = {
        "ok": True,
        "style": style_id,
        "valid": True,
        "normalized_params": result.normalized_params,
        "warnings": result.warnings,
        "fonts": [fp.to_dict() for fp in result.fonts_used],
        "view_box": list(result.view_box),
        "canonical_size_mm": (
            list(result.canonical_size_mm) if result.canonical_size_mm else None
        ),
    }
    if json_out:
        out_mod.emit_json(report)
    else:
        click.echo(f"style {style_id}: VALID")
        click.echo(f"  viewBox: {result.view_box}")
        if result.warnings:
            for w in result.warnings:
                click.echo(f"  warning: {w}")
        for fp in result.fonts_used:
            click.echo(f"  font: {fp.family}  {fp.file_path}")


# ──────────────────────────────────────────────────────────────────────────────
# agent-info, list, doctor, fonts, colors
# ──────────────────────────────────────────────────────────────────────────────
@cli.command(name="agent-info")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON (default).")
def agent_info(json_out):
    """Full machine-readable capability manifest (styles, params, fonts, colors)."""
    # agent-info is JSON-first; the flag exists for symmetry/explicitness.
    click.echo(manifest.to_json())


@cli.command(name="list")
@click.argument("query", required=False, default="")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON.")
def list_styles(query, json_out):
    """Browse or search styles: stamp list signature | oval | office."""
    specs = [s for s in styles.all() if all(word in
             f"{s.META.id} {s.META.title} {s.META.description}".lower()
             for word in query.lower().split())]
    if json_out:
        out_mod.emit_json({
            "ok": True,
            "styles": [
                {"id": s.META.id, "country": s.META.country, "shape": s.META.shape,
                 "title": s.META.title}
                for s in specs
            ],
            "load_errors": [
                {"module": e.module, "error": e.error} for e in styles.load_errors()
            ],
        })
        return
    if not specs:
        click.echo(f"No styles match '{query}'. Try `stamp list` for the full catalog.")
    for s in specs:
        m = s.META
        click.echo(f"  {m.id:30s} {m.country:4s} {m.shape:10s} {m.title}")
    errs = styles.load_errors()
    if errs:
        click.echo("\nload errors:", err=True)
        for e in errs:
            click.echo(f"  {e.module}: {e.error}", err=True)


@cli.command(name="inspect")
@click.argument("path", type=click.Path(dir_okay=False))
@click.option("--json", "json_out", is_flag=True, help="Emit the reference and SHA-256 as JSON.")
def inspect_artifact(path, json_out):
    """Read a saved graphic's reference and checksum without its source image.

    Record the SHA-256 separately to check this exact file later with `stamp verify`.
    """
    try:
        report = provenance.inspect_file(path)
    except (OSError, StampError) as e:
        raise SystemExit(_fail(str(e), e.exit_code if isinstance(e, StampError) else out_mod.EXIT_IO_ERROR,
                               None, json_out))
    if json_out:
        out_mod.emit_json(report)
    else:
        click.echo(f"Reference  {report['reference'] or '(no embedded reference)'}")
        click.echo(f"SHA-256    {report['sha256']}")
        click.echo(f"Format     {report['format'].upper()}  {report['size'][0]} × {report['size'][1]}")


@cli.command(name="verify")
@click.argument("path", type=click.Path(dir_okay=False))
@click.option("--sha256", "expected", required=True, help="Original file checksum recorded at export or with `stamp inspect`.")
@click.option("--json", "json_out", is_flag=True)
def verify_artifact(path, expected, json_out):
    """Check a graphic against a separately recorded SHA-256. Does not authenticate a signer."""
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        raise SystemExit(_fail("--sha256 must contain 64 hexadecimal characters.", EXIT_USER_ERROR, None, json_out))
    try:
        report = provenance.inspect_file(path)
    except (OSError, StampError) as e:
        raise SystemExit(_fail(str(e), e.exit_code if isinstance(e, StampError) else out_mod.EXIT_IO_ERROR,
                               None, json_out))
    matches = report["sha256"] == expected.lower()
    report.update(ok=matches, matches=matches)
    if json_out:
        out_mod.emit_json(report)
    else:
        click.echo("MATCH — file is unchanged." if matches else "MISMATCH — file differs from the recorded checksum.")
    if not matches:
        raise SystemExit(EXIT_USER_ERROR)


@cli.command(name="preview")
@click.option("--style", "style_ids", multiple=True, help="Preview only this style ID (repeatable).")
@click.option("--output", "-o", default="stamp-preview.html", type=click.Path(dir_okay=False), show_default=True)
@click.option("--open", "open_result", is_flag=True, help="Open the offline gallery in your browser.")
@click.option("--force", is_flag=True, help="Replace an existing gallery.")
@click.option("--json", "json_out", is_flag=True)
def preview_styles(style_ids, output, open_result, force, json_out):
    """Browse synthetic examples, at print proportions, in an offline HTML gallery."""
    from .preview import gallery
    path = Path(output).expanduser()
    try:
        if path.suffix.lower() not in (".html", ".htm"):
            raise out_mod.UserError("The preview gallery needs an .html output path.")
        out_mod.check_paths([path], force=force)
        specs = styles.all() if not style_ids else [styles.get(s) for s in style_ids]
        if any(spec is None for spec in specs):
            raise out_mod.UserError("Unknown preview style. Use `stamp list` to find its ID.")
        page, errors = gallery(specs)
        out_mod.write_artifacts({path: page.encode("utf-8")}, force=force)
    except (OSError, StampError) as e:
        raise SystemExit(_fail(str(e), e.exit_code if isinstance(e, StampError) else out_mod.EXIT_IO_ERROR,
                               None, json_out))
    if open_result:
        click.launch(str(path.resolve()))
    if json_out:
        out_mod.emit_json({"ok": not errors, "path": str(path), "styles": len(specs), "errors": errors})
    else:
        click.echo(f"wrote {path}")
        if errors:
            click.echo(f"{len(errors)} preview(s) unavailable. Run `stamp doctor` for details.", err=True)
    if errors:
        raise SystemExit(EXIT_FONT_MISSING)


# A tiny fixture exercising the three resvg features the spike worried about:
# <textPath>, dominant-baseline=central CJK, and the ❋ glyph.
_DOCTOR_SVG = (
    '<svg version="1.1" xmlns="http://www.w3.org/2000/svg" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" width="200" height="120" '
    'viewBox="0 0 200 120">'
    '<defs><path id="dp" d="M 20,60 a 80,40 0 0,1 160,0"/></defs>'
    '<text font-family="{en}" font-size="18" fill="#FF0000">'
    '<textPath startOffset="50%" text-anchor="middle" href="#dp">TEST ❋</textPath></text>'
    '<text font-family="{zh}" font-size="22" fill="#FF0000" text-anchor="middle" '
    'dominant-baseline="central" x="100" y="95">印章</text>'
    '</svg>'
)


@cli.command(name="doctor")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON.")
def doctor(json_out):
    """Health check: render a textPath + CJK + ❋ fixture; report resvg + fonts."""
    report: dict[str, Any] = {"ok": True, "checks": {}}
    overall_ok = True

    # 1. Rasterizer present?
    try:
        report["checks"]["resvg"] = {
            "ok": True,
            "binding_version": raster_mod.binding_version(),
            "engine_version": raster_mod.resvg_version(),
        }
    except RasterizerMissingError as e:
        overall_ok = False
        report["checks"]["resvg"] = {"ok": False, "error": str(e)}

    # 2. Fonts: at least one CJK + one Latin.
    resolver = fonts_mod.FontResolver(allow_fetch=False)
    cjk = resolver.first_available(fonts_mod.CJK_ALIASES)
    latin = resolver.first_available(fonts_mod.LATIN_ALIASES)
    symbols = resolver.try_resolve("symbols")
    report["checks"]["fonts"] = {
        "ok": bool(cjk and latin),
        "cjk": cjk.to_dict() if cjk else None,
        "latin": latin.to_dict() if latin else None,
        "symbols": symbols.to_dict() if symbols else None,
        "available": [
            {"alias": a, "path": p} for a, p, _c, _l in resolver.listing() if p
        ],
    }
    if not (cjk and latin):
        overall_ok = False

    # 3. Render the fixture (textPath + central baseline + ❋).
    fixture = {"ok": False}
    if report["checks"]["resvg"].get("ok"):
        en = symbols or latin
        zh = cjk
        font_files = [fp.file_path for fp in (en, zh) if fp]
        svg = _DOCTOR_SVG.format(
            en=(en.family if en else "sans-serif"),
            zh=(zh.family if zh else "sans-serif"),
        )
        try:
            png = raster_mod.render_png(
                svg, font_files=font_files, width=200,
                background="white", skip_system_fonts=bool(font_files),
            )
            fixture = {"ok": len(png) > 0, "png_bytes": len(png)}
        except RasterizerMissingError as e:
            fixture = {"ok": False, "error": str(e)}
            overall_ok = False
    report["checks"]["fixture"] = fixture
    if not fixture.get("ok"):
        overall_ok = False

    # 4. Registry load errors.
    errs = styles.load_errors()
    report["checks"]["registry"] = {
        "ok": len(errs) == 0,
        "styles_loaded": len(styles.REGISTRY),
        "load_errors": [{"module": e.module, "error": e.error} for e in errs],
    }
    # Load errors are surfaced but do not by themselves fail doctor (a broken
    # third-party style shouldn't make the whole tool report unhealthy).

    report["ok"] = overall_ok

    if json_out:
        out_mod.emit_json(report)
    else:
        r = report["checks"]
        rv = r["resvg"]
        if rv.get("ok"):
            click.echo(f"resvg:    OK  binding {rv['binding_version']}  "
                       f"engine {rv['engine_version']}")
        else:
            click.echo(f"resvg:    MISSING  {rv.get('error')}")
        fr = r["fonts"]
        click.echo(f"fonts:    {'OK' if fr['ok'] else 'MISSING'}  "
                   f"cjk={fr['cjk']['family'] if fr['cjk'] else '-'}  "
                   f"latin={fr['latin']['family'] if fr['latin'] else '-'}  "
                   f"symbols={'yes' if fr['symbols'] else 'no'}")
        click.echo(f"fixture:  {'OK' if fixture.get('ok') else 'FAIL'}  "
                   f"({fixture.get('png_bytes', 0)} png bytes)")
        reg = r["registry"]
        click.echo(f"registry: {reg['styles_loaded']} styles loaded, "
                   f"{len(reg['load_errors'])} load error(s)")
        for e in reg["load_errors"]:
            click.echo(f"  - {e['module']}: {e['error']}", err=True)
        click.echo(f"\noverall:  {'OK' if overall_ok else 'PROBLEMS'}")

    raise SystemExit(EXIT_OK if overall_ok else EXIT_FONT_MISSING)


@cli.command(name="fonts")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON.")
@click.option("--fetch", is_flag=True, help="Fetch the OFL Noto Sans Symbols if missing.")
def fonts_cmd(json_out, fetch):
    """List font aliases and where they resolve on this machine."""
    resolver = fonts_mod.FontResolver(allow_fetch=fetch)
    if fetch:
        try:
            resolver.symbols()
            resolver.symbols2()
        except FontMissingError as e:
            click.echo(f"fetch failed: {e}", err=True)
            raise SystemExit(EXIT_FONT_MISSING)
    rows = resolver.listing()
    if json_out:
        out_mod.emit_json({
            "ok": True,
            "fonts": [
                {"alias": a, "path": p, "available": p is not None,
                 "cjk": c, "latin": l}
                for a, p, c, l in rows
            ],
        })
        return
    for alias, path, c, l in rows:
        mark = "ok  " if path else "MISS"
        kinds = "".join([("C" if c else "-"), ("L" if l else "-")])
        click.echo(f"  [{mark}] {kinds} {alias:12s} {path or '(not found)'}")


@cli.command(name="colors")
@click.option("--json", "json_out", is_flag=True, help="Emit JSON.")
def colors_cmd(json_out):
    """List ink-color presets (STAMP4U palette + cinnabar inks)."""
    rows = colors_mod.listing()
    if json_out:
        out_mod.emit_json({
            "ok": True,
            "colors": [{"name": n, "hex": h, "family": fam} for n, h, fam in rows],
        })
        return
    for name, hexv, fam in rows:
        click.echo(f"  {name:14s} {hexv}  ({fam})")


# Materialize the nested style groups at import time (after all commands exist).
_build_nested_groups()

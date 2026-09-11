"""Result writing, JSON envelopes, and semantic exit codes.

One place owns: how a :class:`~stamp_cli.styles.base.StyleResult` becomes files
on disk (or bytes on stdout), what the machine-readable JSON envelope looks like,
and which integer exit code each failure class maps to.

Exit codes (PLAN.md §8):
    0  ok
    1  user error          (bad params, unknown style, bad color/format)
    2  font / runtime missing
    3  rasterizer missing  (resvg_py unavailable / render failure)
    4  I/O error           (cannot write output)
"""

from __future__ import annotations

import json
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# ── Exit codes ────────────────────────────────────────────────────────────────
EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_FONT_MISSING = 2
EXIT_RASTERIZER_MISSING = 3
EXIT_IO_ERROR = 4


class StampError(Exception):
    """Base for errors that carry a semantic exit code."""

    exit_code = EXIT_USER_ERROR

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class UserError(StampError):
    exit_code = EXIT_USER_ERROR


class IOErrorStamp(StampError):
    exit_code = EXIT_IO_ERROR


def emit_json(payload: dict, *, stream=None) -> None:
    """Write a JSON envelope (one line, UTF-8 preserved) to a stream."""
    stream = stream or sys.stdout
    stream.write(json.dumps(payload, ensure_ascii=False))
    stream.write("\n")
    stream.flush()


def error_envelope(message: str, *, code: int, style: str | None = None,
                 **extra: Any) -> dict:
    """Build the standard error envelope."""
    env: dict = {"ok": False, "error": message, "exit_code": code}
    if style is not None:
        env["style"] = style
    env.update(extra)
    return env


def _infer_formats(output: str | None, fmt: str | None, stdout: bool) -> tuple[bool, bool]:
    """Decide whether to write SVG and/or PNG.

    Rules (PLAN.md §8):
      * explicit ``fmt`` ('svg'|'png'|'both') wins.
      * else infer from the output path extension: ``.svg`` -> svg, ``.png`` ->
        png, no extension / directory -> both.
      * stdout with no explicit fmt defaults to png (a single binary stream).
    Returns ``(want_svg, want_png)``.
    """
    if fmt == "svg":
        return True, False
    if fmt == "png":
        return False, True
    if fmt == "both":
        return True, True
    # infer
    if output:
        ext = Path(output).suffix.lower()
        if ext == ".svg":
            return True, False
        if ext == ".png":
            return False, True
        # no/unknown extension -> both
        return True, True
    if stdout:
        return False, True  # single stream -> png
    # default
    return True, True


def output_paths(output: str | None, fmt: str | None, stdout: bool,
                 *, force: bool = False, open_result: bool = False) -> dict[str, Path]:
    """Validate destinations before resolving fonts or rendering anything."""
    if stdout:
        if output or open_result or fmt == "both":
            raise UserError("--stdout needs one format and cannot be combined with --output or --open.")
        return {}
    if not output:
        raise UserError("Choose --output/-o PATH, or --stdout for a single artifact.")
    out = Path(output).expanduser()
    if out.suffix and out.suffix.lower() not in (".svg", ".png") and not fmt:
        raise UserError("Use a .svg or .png extension, no extension for both, or choose --format.")
    want_svg, want_png = _infer_formats(output, fmt, False)
    paths = {kind: out.with_suffix('.' + kind) for kind, want in
             (("svg", want_svg), ("png", want_png)) if want}
    check_paths(paths.values(), force=force)
    return paths


def check_paths(paths, *, force: bool = False) -> None:
    for path in paths:
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise IOErrorStamp(f"Output must be a regular file: {path}")
        if path.exists() and not force:
            raise UserError(f"Output already exists: {path}. Choose another name or use --force.")


def write_artifacts(artifacts: dict[Path, bytes], *, force: bool = False) -> None:
    """Stage the complete export; roll back files on a write failure.

    Each installation is atomic. A multi-file export is rolled back on ordinary
    I/O errors, though no filesystem transaction can cover a process/power loss.
    Hard-link installation without --force never overwrites a concurrent file.
    Temporary and newly written artifacts are owner-readable/writable only.
    """
    check_paths(artifacts, force=force)
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    installed: list[Path] = []
    try:
        for path, data in artifacts.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".stamp-", delete=False) as f:
                staged[path] = Path(f.name)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        for path, temp in staged.items():
            # Recheck after rendering/staging; avoid replacing a new symlink.
            check_paths([path], force=force)
            if force:
                if path.exists():
                    fd, backup = tempfile.mkstemp(dir=path.parent, prefix=".stamp-backup-")
                    os.close(fd)
                    os.unlink(backup)
                    os.link(path, backup)
                    backups[path] = Path(backup)
                os.replace(temp, path)
            else:
                os.link(temp, path)
            installed.append(path)
    except (OSError, StampError) as e:
        rollback_errors = []
        for path in reversed(installed):
            try:
                if path in backups:
                    os.replace(backups.pop(path), path)
                else:
                    path.unlink()
            except OSError as rollback:
                rollback_errors.append(str(rollback))
        if rollback_errors:
            # Preserve backup files for recovery if rollback itself fails.
            raise IOErrorStamp(f"Export failed: {e}; recovery needed: {'; '.join(rollback_errors)}") from e
        for backup in backups.values():
            backup.unlink(missing_ok=True)
        if isinstance(e, StampError):
            raise
        raise IOErrorStamp(f"Failed to write output: {e}") from e
    finally:
        for temp in staged.values():
            temp.unlink(missing_ok=True)
    for backup in backups.values():
        backup.unlink(missing_ok=True)


def write_result(
    *,
    svg: str,
    png_bytes_provider,
    style_id: str,
    output: str | None,
    fmt: str | None,
    stdout: bool,
    json_out: bool,
    background: str,
    width: int | None,
    dpi: int | None,
    extra: dict | None = None,
    force: bool = False,
    open_result: bool = False,
) -> int:
    """Write a style result to disk or stdout and (optionally) print an envelope.

    Args:
        svg: the SVG document string.
        png_bytes_provider: a zero-arg callable returning PNG bytes. Called lazily
            so SVG-only runs never invoke the rasterizer. May raise
            ``RasterizerMissingError``; the caller is expected to translate that
            to exit code 3 before reaching here, but we guard anyway.
        style_id: id of the style, echoed into the envelope.
        output: destination path (without or with extension), or ``None``.
        fmt: explicit ``'svg'|'png'|'both'`` or ``None`` to infer.
        stdout: write a single artifact's bytes to stdout instead of disk.
        json_out: emit a JSON envelope on stdout describing what was written.
        background, width, dpi: echoed into the envelope for reproducibility.
        extra: extra fields merged into the envelope (warnings, fonts, size…).

    Returns:
        An exit code (``EXIT_OK`` on success).

    Raises:
        UserError / IOErrorStamp for conditions the caller maps to exit codes.
    """
    paths = output_paths(output, fmt, stdout, force=force, open_result=open_result)
    want_svg, want_png = _infer_formats(output, fmt, stdout)

    # ── stdout: exactly one artifact ─────────────────────────────────────────
    if stdout:
        if want_svg and want_png:
            # ambiguous on a single stream — prefer png unless fmt said svg
            want_svg, want_png = False, True
        if want_png:
            data = png_bytes_provider()
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            paths = {"stdout": "png"}
        else:
            data = svg.encode("utf-8")
            sys.stdout.write(svg)
            sys.stdout.flush()
            paths = {"stdout": "svg"}
        # JSON envelope would corrupt a binary stdout stream, so when --json is
        # combined with --stdout we send the envelope to stderr.
        if json_out:
            emit_json(
                {
                    "ok": True,
                    "style": style_id,
                    "stdout": paths["stdout"],
                    "format": paths["stdout"],
                    "background": background,
                    "width": width,
                    "dpi": dpi,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    **(extra or {}),
                },
                stream=sys.stderr,
            )
        return EXIT_OK

    # ── disk ─────────────────────────────────────────────────────────────────
    # Finish *all* rendering before touching the destinations.
    artifacts = {path: svg.encode("utf-8") if kind == "svg" else png_bytes_provider()
                 for kind, path in paths.items()}
    checksums = {kind: hashlib.sha256(artifacts[path]).hexdigest() for kind, path in paths.items()}
    write_artifacts(artifacts, force=force)
    written = {kind: str(path) for kind, path in paths.items()}
    if open_result:
        import click
        if click.launch(str((paths.get("png") or paths["svg"]).resolve())):
            (extra or {}).setdefault("warnings", []).append("Saved successfully; could not open the default viewer.")

    if json_out:
        primary = written.get("png") or written.get("svg")
        emit_json(
            {
                "ok": True,
                "style": style_id,
                "path": primary,
                "paths": written,
                "format": fmt or ("both" if len(written) > 1 else next(iter(written))),
                "background": background,
                "width": width,
                "dpi": dpi,
                "checksums": checksums,
                **(extra or {}),
            }
        )
    else:
        for warning in (extra or {}).get("warnings", []):
            sys.stderr.write(f"warning: {warning}\n")
        for kind, p in written.items():
            sys.stdout.write(f"wrote {p}\n")
        if (extra or {}).get("reference"):
            sys.stdout.write(f"reference {(extra or {})['reference']}\n")
        sys.stdout.flush()
    return EXIT_OK

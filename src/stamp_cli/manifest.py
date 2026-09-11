"""Build the machine-readable ``agent-info`` manifest from the style registry.

An AI agent reads this to learn the entire surface: every style, its country /
shape / canonical size, the JSON schema of its parameters (derived from
``PARAMS``), and a ready-to-run example. The manifest is generated from the
registry, so a newly auto-discovered style appears here with zero extra work.
"""

from __future__ import annotations

import json
from typing import Any

from . import styles
from ._version import __version__
from .core import colors as colors_mod
from .core import fonts as fonts_mod
from .examples import SAMPLES

VERSION = __version__

# JSON-schema type name for each Python type a ParamSpec may declare.
_TYPE_NAMES = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
}


def _json_safe(value: Any) -> bool:
    """True if ``value`` can go straight into the manifest JSON.

    Styles may use a private sentinel object as a param default (e.g. hk.rect's
    "use the preset's value" marker). Such an object must never reach the
    serialized manifest, so we screen every default/example value through this.
    """
    try:
        json.dumps(value, ensure_ascii=False)
        return True
    except (TypeError, ValueError):
        return False


def _param_schema(param: "styles.ParamSpec") -> dict:
    """Translate one ParamSpec into a JSON-schema-ish property dict."""
    schema: dict[str, Any] = {
        "type": _TYPE_NAMES.get(param.type, "string"),
        "description": param.help,
        "required": param.required,
    }
    # Only expose a default if it is JSON-representable (skip sentinel objects).
    if param.default is not None and _json_safe(param.default):
        schema["default"] = param.default
    if param.enum:
        schema["enum"] = [e for e in param.enum if _json_safe(e)]
    return schema


def _example_params(spec: "styles.StyleSpec") -> dict:
    """Return a fictional runnable sample, with defaults as a fallback.

    The shared sample catalog also feeds the preview gallery. If a third-party
    style has no sample, synthesize one from its defaults and required fields.
    """
    sample = SAMPLES.get(spec.META.id)
    if sample is not None:
        return {key: value for key, value in sample.items() if _json_safe(value)}

    example: dict[str, Any] = {}
    defaults = getattr(spec, "DEFAULTS", {}) or {}
    for param in spec.PARAMS:
        if param.name in defaults and defaults[param.name] is not None and _json_safe(defaults[param.name]):
            example[param.name] = defaults[param.name]
        elif param.default is not None and _json_safe(param.default):
            example[param.name] = param.default
        elif param.required:
            example[param.name] = f"<{param.name}>"
    return example


def style_entry(spec: "styles.StyleSpec") -> dict:
    """Build the manifest entry for a single style."""
    meta = spec.META
    params_schema = {p.name: _param_schema(p) for p in spec.PARAMS}
    example_params = _example_params(spec)
    return {
        "id": meta.id,
        "country": meta.country,
        "shape": meta.shape,
        "title": meta.title,
        "description": meta.description,
        "canonical_size_mm": list(meta.canonical_size_mm) if meta.canonical_size_mm else None,
        "reference": meta.reference,
        "params": params_schema,
        "example": {
            "command": f"stamp generate --style {meta.id} --params - -o output",
            "params": example_params,
        },
    }


def build_manifest(*, resolver: "fonts_mod.FontResolver | None" = None) -> dict:
    """Assemble the full agent-info manifest dict."""
    # Introspection stays offline. Font downloads are an explicit
    # `stamp fonts --fetch` operation.
    resolver = resolver or fonts_mod.FontResolver(allow_fetch=False)
    style_specs = styles.all()

    fonts_available = [
        {"alias": alias, "path": path, "cjk": cjk, "latin": latin}
        for alias, path, cjk, latin in resolver.listing()
    ]

    load_errs = [
        {"module": e.module, "error": e.error} for e in styles.load_errors()
    ]

    return {
        "name": "stamp",
        "version": VERSION,
        "summary": (
            "Generate signature graphics, company seals, personal chops, and "
            "office stamps as physically sized SVG and print-ready PNG files."
        ),
        "render_model": {
            "primitive": "SVG string",
            "rasterizer": "resvg_py",
            "note": "Each style is a pure function params -> SVG; PNG is rasterized from it.",
        },
        "machine_entrypoint": {
            "command": "stamp generate --style <id> --params <file|-> -o <output>",
            "stdin": "stamp generate --style <id> --params - -o <output>",
            "schema": "stamp agent-info --json",
        },
        "styles": [style_entry(s) for s in style_specs],
        "shared_flags": {
            "--bg / --background": "Background for both SVG and PNG: transparent | white | <color>.",
            "--size / --px-width": "PNG width in pixels (16..8192); mutually exclusive with --dpi.",
            "--dpi": "PNG print resolution (36..2400; default 300); mutually exclusive with --size.",
            "--width-mm": "Printed width in millimetres (5..300); preserves proportions.",
            "--output / -o": "Destination path; .svg/.png selects one format, no extension selects both.",
            "--format": "Force svg | png | both; overrides the path extension.",
            "--stdout": "Write one artifact's bytes to stdout.",
            "--json": "Emit a JSON result or error; with --stdout it is written to stderr.",
            "--force": "Replace existing output files; otherwise they are protected.",
            "--open": "Open the saved result in the default viewer.",
            "--weathered": "Add the same subtle ink wear to SVG and PNG.",
            "--seed": "Reproducible weathering seed; requires --weathered.",
        },
        "inspection": {
            "preview": "stamp preview --open",
            "inspect": "stamp inspect <file>",
            "verify": "stamp verify <file> --sha256 <original-sha256>",
            "fonts": "stamp fonts (offline); stamp fonts --fetch downloads optional Noto symbols",
            "verification_note": (
                "SHA-256 comparison detects changed file bytes; it does not authenticate "
                "a signer or prove legal effect."
            ),
        },
        "signature_reference": {
            "format": "32 uppercase hexadecimal characters",
            "visibility": "stamp sign --show-id / --no-show-id",
            "metadata": "The computed reference remains embedded when it is hidden visually.",
            "meaning": (
                "Content fingerprint for the generated graphic; not identity, consent, "
                "signing time, authentication, a digital certificate, or legal proof."
            ),
        },
        "colors": colors_mod.names(),
        "fonts": fonts_available,
        "load_errors": load_errs,
        "exit_codes": {
            "0": "ok",
            "1": "user error (bad params, unknown style, bad color/format)",
            "2": "font / runtime missing",
            "3": "rasterizer missing",
            "4": "I/O error",
        },
    }


def to_json(*, indent: int | None = 2,
            resolver: "fonts_mod.FontResolver | None" = None) -> str:
    """Serialize the manifest to JSON (UTF-8 preserved)."""
    return json.dumps(build_manifest(resolver=resolver), indent=indent, ensure_ascii=False)

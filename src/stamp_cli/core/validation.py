"""Validate JSON parameters before style code can coerce or ignore them."""
from __future__ import annotations

import difflib
import math


def validate_params(spec, params):
    if not isinstance(params, dict):
        raise ValueError("params JSON must be an object")
    schema = {p.name: p for p in spec.PARAMS}
    for key, value in params.items():
        if key not in schema:
            suggestion = difflib.get_close_matches(key, schema, n=1)
            hint = f" Did you mean '{suggestion[0]}'?" if suggestion else ""
            raise ValueError(f"Unknown parameter '{key}' for {spec.META.id}.{hint}")
        param = schema[key]
        if value is None:
            continue
        expected = param.type
        valid = (isinstance(value, (int, float)) and not isinstance(value, bool)
                 if expected is float else isinstance(value, expected))
        if expected is int and isinstance(value, bool):
            valid = False
        # Click emits tuples for repeatable options; JSON uses arrays.
        if expected is list:
            valid = isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value)
        if not valid:
            raise ValueError(f"Parameter '{key}' must be {expected.__name__}.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"Parameter '{key}' must be finite.")
        if param.enum and value not in param.enum:
            raise ValueError(f"Parameter '{key}' must be one of: {', '.join(map(str, param.enum))}.")
        texts = value if expected is list else [value]
        for text in texts:
            if isinstance(text, str):
                if len(text) > 2000:
                    raise ValueError(f"Parameter '{key}' is too long (maximum 2000 characters).")
                if any((ord(c) < 32 and c not in '\t\n\r') or 0xD800 <= ord(c) <= 0xDFFF
                       or ord(c) in (0xFFFE, 0xFFFF) for c in text):
                    raise ValueError(f"Parameter '{key}' contains invalid XML characters.")
    for key, param in schema.items():
        if param.required and params.get(key) in (None, ""):
            raise ValueError(f"Missing required parameter '{key}'.")
    return params

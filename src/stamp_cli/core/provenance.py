"""A portable graphic reference and an independently recordable file checksum."""
from __future__ import annotations

import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from .output import UserError
from .svg import esc


def record(style, reference=None):
    return {"schema": "stamp-cli/1", "style": style, "reference": reference}


def embed_svg(svg, metadata):
    end = svg.index(">") + 1
    node = '<metadata id="stamp-cli">' + esc(json.dumps(metadata, separators=(",", ":"))) + '</metadata>'
    return svg[:end] + node + svg[end:]


def inspect_file(path):
    path = Path(path).expanduser()
    if path.stat().st_size > 64 * 1024 * 1024:
        raise UserError("Inspection is limited to files up to 64 MiB.")
    data = path.read_bytes()
    metadata = {}
    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            kind = "png"
            with Image.open(io.BytesIO(data)) as image:
                raw = image.info.get("stamp-cli", "{}")
                dimensions = list(image.size)
                metadata = json.loads(raw)
        else:
            kind = "svg"
            if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
                raise ValueError("XML entity declarations are not supported")
            root = ET.fromstring(data)
            if root.tag != "{http://www.w3.org/2000/svg}svg":
                raise ValueError("expected SVG")
            dimensions = [root.attrib.get("width"), root.attrib.get("height")]
            for child in root:
                if child.tag == "{http://www.w3.org/2000/svg}metadata" and child.get("id") == "stamp-cli":
                    metadata = json.loads(child.text or "{}")
                    break
        if not isinstance(metadata, dict):
            raise ValueError("invalid graphic metadata")
        ref = metadata.get("reference")
        if ref is not None and (not isinstance(ref, str) or not re.fullmatch(r"[0-9A-F]{32}", ref)):
            raise ValueError("invalid graphic reference")
    except (ValueError, ET.ParseError, OSError) as e:
        raise UserError(f"Cannot inspect this PNG/SVG: {e}") from e
    return {"ok": True, "path": str(path), "format": kind, "size": dimensions,
            "style": metadata.get("style"), "reference": metadata.get("reference"),
            "sha256": hashlib.sha256(data).hexdigest()}

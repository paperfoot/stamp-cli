"""Print sizing and deterministic finishing shared by every stamp style."""
from __future__ import annotations

import io
import json
import math
import random
import re

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from .output import UserError
from .svg import num


def dimensions(result, *, width_mm=None, size=None, dpi=None):
    if size is not None and dpi is not None:
        raise UserError("Choose --size in pixels or --dpi for print resolution, not both.")
    mm = width_mm if width_mm is not None else (result.canonical_size_mm or (50, 50))[0]
    if not math.isfinite(mm) or not 5 <= mm <= 300:
        raise UserError("--width-mm must be between 5 and 300 mm.")
    height_mm = mm * result.view_box[3] / result.view_box[2]
    pixels = size if size is not None else round(mm / 25.4 * (dpi or 300))
    if not 16 <= pixels <= 8192 or not 16 <= pixels * height_mm / mm <= 8192:
        raise UserError("Rendered width and height must be between 16 and 8192 pixels. Reduce --size or --dpi.")
    actual_dpi = pixels / mm * 25.4
    return mm, height_mm, pixels, actual_dpi


def prepare_svg(result, *, width_mm, height_mm, background="transparent",
                weathered=False, seed=0):
    """Keep the viewBox geometry; give SVG a real physical size and background."""
    source = result.svg
    end = source.index(">") + 1
    root = source[:end]
    root = re.sub(r'\bwidth="[^"]*"', f'width="{num(width_mm)}mm"', root, count=1)
    root = re.sub(r'\bheight="[^"]*"', f'height="{num(height_mm)}mm"', root, count=1)
    body = source[end:source.rindex("</svg>")]
    x, y, w, h = result.view_box
    background_el = ""
    if background not in ("transparent", "none"):
        background_el = (f'<rect x="{num(x)}" y="{num(y)}" width="{num(w)}" '
                         f'height="{num(h)}" fill="{background}"/>')
    if weathered:
        rng = random.Random(seed)
        holes = []
        # Vector holes scale with the seal and look identical in SVG and PNG.
        unit = min(w, h) / 200
        for _ in range(min(3000, max(200, round(w * h / (110 * unit * unit))))):
            holes.append(f'<ellipse cx="{num(x + rng.random() * w)}" '
                         f'cy="{num(y + rng.random() * h)}" '
                         f'rx="{num(rng.uniform(.22, .75) * unit)}" '
                         f'ry="{num(rng.uniform(.22, .9) * unit)}" fill="black"/>')
        mask = (f'<defs><mask id="stamp-wear" maskUnits="userSpaceOnUse" '
                f'x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}">'
                f'<rect x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}" fill="white"/>'
                + ''.join(holes) + '</mask></defs>')
        body = mask + '<g mask="url(#stamp-wear)">' + body + '</g>'
    return root + background_el + body + '</svg>'


def with_resolution(png: bytes, dpi: float, metadata=None) -> bytes:
    """Write PNG pHYs without retaining image metadata or filesystem details."""
    with Image.open(io.BytesIO(png)) as image:
        image.load()
        image.info.clear()
        output = io.BytesIO()
        info = PngInfo()
        if metadata:
            info.add_text("stamp-cli", json.dumps(metadata, separators=(",", ":")))
        image.save(output, format="PNG", dpi=(dpi, dpi), pnginfo=info)
        return output.getvalue()

"""``esign.signature`` — DocuSign-style electronic-signature overlay.

The familiar e-signature badge: an accent-colored bracket *open on the right*
(a rounded "C" by default), a small bold ``Signed by:`` label on top, the
handwritten signature in the middle with its white paper background knocked out
to transparent, and a deterministic 32-hex unique ID along the bottom — exactly
the anatomy DocuSign stamps onto a signed PDF.

Three ways to supply the signature, all deterministic:

* a **path** to a scan/photo of a handwritten signature (PNG/JPG/…): its white
  background is removed by a luminance ramp and the ink is embedded as a PNG
  ``<image>`` data-URI inside the SVG (resvg rasterizes it natively);
* ``sample`` (the default) — a synthetic, non-PII squiggle generated at runtime
  so the zero-argument demo and the registry test-suite always have a real
  signature to flow through the full pipeline without shipping anyone's mark;
* ``typed`` / ``name`` / ``cursive`` — render ``--name`` in a cursive script
  font (DocuSign's "adopt a typed signature"), no image required.

The unique ID is a **content hash** — ``SHA-256`` of the signer + the signature's
RAW (pre-compression) pixels, truncated to 32 uppercase hex — never a random
GUID or a timestamp, so the SAME signer + signature always yields the SAME ID on
any machine. (Hashing the *raw* pixels rather than the encoded PNG is deliberate:
a PNG's deflate bytes vary across zlib/Pillow builds, so a compressed-byte hash
would drift between hosts.) The embedded ``<image>`` PNG bytes themselves are
deterministic within a build but, being a compressed raster, are not guaranteed
byte-identical across Pillow/zlib versions; the SVG structure and the ID are.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
import unicodedata
import warnings as warnings_mod
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps

from ...core import colors as colors_mod
from ...core import svg
from ...core.text import fitted_text
from ...core.fonts import LATIN_ALIASES, FontMissingError, default_resolver
from ..base import ParamSpec, StyleMeta, StyleResult

# Bump when geometry/defaults change in a way that would alter golden output.
_VERSION = "3"
_ID_VERSION = "1"  # Layout revisions must not renumber an unchanged image mark.

# ── Fixed canvas + layout (SVG units; physical ~60×29 mm at the canonical scale)
_VIEW_BOX: tuple[float, float, float, float] = (0.0, 0.0, 420.0, 200.0)
_W, _H = 420.0, 200.0

# Bracket box (inset from the viewBox edges) and its chrome.
_M = 8.0                       # outer inset
_SW = 3.0                      # bracket stroke width
_R = 16.0                      # corner radius (round + full variants)
# Length of the top/bottom arms for the left-anchored brackets (round/square).
# Short arms (~28% of the width) leave the right clearly OPEN and let the
# signature overflow past them — the DocuSign "[" / "C" look, not a full box.
_ARM = 110.0
_X0, _Y0, _X1, _Y1 = _M, _M, _W - _M, _H - _M

# Content zones, laid out top→bottom: label / signature band / ID.
_CONTENT_X = 28.0              # left text x (clear of the bracket's left edge)
_CONTENT_W = 368.0            # usable text width
_CONTENT_RIGHT = _CONTENT_X + _CONTENT_W  # = 396
_Y_LABEL = 38.0; _LAB_SIZE = 18
_Y_ID = 178.0; _ID_SIZE = 14; _ID_LS = 1.2
_BAND_X, _BAND_Y, _BAND_W, _BAND_H = 28.0, 50.0, 368.0, 104.0

_SAMPLE_TOKENS = {"", "sample", "demo"}
_TYPED_TOKENS = {"typed", "type", "name", "cursive", "text"}
_BRACKETS = ("round", "square", "full", "none")
_HEX32 = re.compile(r"[0-9A-F]{32}")


# ── Text fitting ───────────────────────────────────────────────────────────
def _has_non_latin(text: str) -> bool:
    """True if any char is outside the Latin/punctuation range a Latin face covers."""
    return any(ord(c) > 0x2E7F for c in text)


# ── Signature image handling ────────────────────────────────────────────────
def _make_sample_image() -> Image.Image:
    """A synthetic dark-on-white scrawl — nobody's real signature (PII-safe).

    Born on a white background so it flows through the *same* knockout pipeline
    a real scan does, giving the default/test path genuine coverage.
    """
    img = Image.new("RGBA", (600, 200), (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    ink = (22, 28, 60, 255)
    d.line(
        [(36, 150), (120, 60), (196, 150), (276, 66), (356, 150), (440, 72), (540, 128)],
        fill=ink, width=8, joint="curve",
    )
    d.line([(60, 168), (520, 168)], fill=ink, width=3)
    return img


def _open_image(path: Path) -> Image.Image:
    """Open + fully decode a signature image, mapping failures to ValueError."""
    if not path.is_file():
        raise ValueError(f"signature image not found: {path}")
    try:
        with warnings_mod.catch_warnings():
            warnings_mod.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as img:
                if img.width * img.height > 25_000_000:
                    raise ValueError("Signature images are limited to 25 megapixels; resize the scan first.")
                if getattr(img, "n_frames", 1) > 1:
                    raise ValueError("Use a single-frame signature image, not an animation or multi-page scan.")
                img.load()
                return img.copy()
    except Exception as e:  # noqa: BLE001 — any failure to decode a user file is a user error
        # Covers UnidentifiedImageError, OSError, DecompressionBomb{Error,Warning}
        # and exotic per-plugin decoder exceptions; all map to a clean exit 1.
        raise ValueError(f"could not read signature image: {path}: {e}") from e


def _process_image(
    pil: Image.Image, *, low: int, high: int,
    recolor_rgb: tuple[int, int, int] | None, max_px: int, warnings: list[str],
) -> tuple[bytes, tuple[int, int], bytes] | None:
    """Knock out the white background, optionally recolor, crop, re-encode PNG.

    Returns ``(png_bytes, (w, h), raw_tag)`` or ``None`` when the image is blank
    after knockout (no ink found). ``raw_tag`` is the version-independent raw
    pixel payload used to hash the unique ID. The PNG is re-encoded metadata-free
    (no tIME/tEXt/pHYs/iCCP) so it carries nothing host-specific.
    """
    img = ImageOps.exif_transpose(pil)
    # The decoder caps source images at 25 MP. Crop the ink before downscaling:
    # a large white sheet must not reduce the resolution of a small signature.
    img = img.convert("RGBA")

    # Luminance ramp → alpha: dark ink opaque, white paper transparent, a linear
    # ramp between the thresholds preserving anti-aliased stroke edges.
    span = high - low
    lut = [255 if v <= low else (0 if v >= high else round(255 * (high - v) / span))
           for v in range(256)]
    alpha = img.convert("L").point(lut)

    # Respect any pre-existing transparency instead of double-compositing.
    existing = img.getchannel("A")
    if existing.getextrema() != (255, 255):
        alpha = ImageChops.multiply(alpha, existing)

    base = Image.new("RGB", img.size, recolor_rgb) if recolor_rgb is not None else img.convert("RGB")
    out = base.convert("RGBA")
    out.putalpha(alpha)

    bbox = alpha.getbbox()
    if bbox is None:
        return None
    out = out.crop(bbox)
    if max(out.size) > max_px:
        out.thumbnail((max_px, max_px), Image.LANCZOS)
        warnings.append(f"signature downscaled to ≤ {max_px}px")
    # Drop any inherited ICC/EXIF/dpi so the PNG encoder writes no extra chunks
    # (keeps the embed metadata-free and the ID independent of source profiles).
    out.info = {}

    # Hash the ID over the RAW pixels (+ dims + mode), NOT the compressed PNG,
    # so the ID is identical across zlib/Pillow builds (deflate bytes are not).
    raw_tag = out.tobytes() + b"\x1f" + repr(out.size).encode("ascii") + b"\x1f" + out.mode.encode("ascii")

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue(), out.size, raw_tag


# ── Unique ID ─────────────────────────────────────────────────────────────────
def _compute_id(name: str, content_tag: bytes) -> str:
    """Deterministic 32-uppercase-hex ID bound to the signer + signature bytes."""
    h = hashlib.sha256()
    h.update(b"esign.signature\x1f")
    h.update(_ID_VERSION.encode("ascii") + b"\x1f")
    h.update(unicodedata.normalize("NFC", name.strip()).encode("utf-8") + b"\x1f")
    h.update(content_tag)
    return h.hexdigest()[:32].upper()


def _resolve_id(raw: object, name: str, content_tag: bytes, warnings: list[str]) -> str:
    """Resolve the ID param: ``auto`` → content hash; 32-hex → verbatim; else hash."""
    s = str(raw).strip()
    if s.lower() in ("", "auto"):
        return _compute_id(name, content_tag)
    norm = re.sub(r"[\s-]", "", s).upper()
    if _HEX32.fullmatch(norm):
        return norm
    warnings.append(f"sig_id {raw!r} is not 32 hex chars; derived a stable ID from it.")
    return hashlib.sha256(("override:" + s).encode("utf-8")).hexdigest()[:32].upper()


# ── Bracket geometry (open on the right) ───────────────────────────────────────
def _bracket(kind: str, accent: str, extra_height: float = 0) -> str:
    """Build the bracket SVG for ``kind`` (round/square/full/none).

    ``round`` and ``square`` are LEFT-ANCHORED brackets open on the right: a
    full-height left edge with short top/bottom arms (``_ARM`` long), so the
    signature overflows past the open side — the DocuSign ``[`` / ``C`` look.
    ``full`` is a closed rounded rectangle enclosing everything.
    """
    n = svg.num
    y1 = _Y1 + extra_height
    if kind == "none":
        return ""
    if kind == "full":
        return (
            f'<rect x="{n(_X0)}" y="{n(_Y0)}" width="{n(_X1 - _X0)}" '
            f'height="{n(y1 - _Y0)}" rx="{n(_R)}" ry="{n(_R)}" fill="none" '
            f'stroke="{accent}" stroke-width="{n(_SW)}"/>'
        )
    if kind == "square":
        # '[' — sharp corners, short top/bottom arms, open on the right.
        d = (
            f"M {n(_X0 + _ARM)} {n(_Y0)} H {n(_X0)} V {n(y1)} "
            f"H {n(_X0 + _ARM)}"
        )
        return (
            f'<path d="{d}" fill="none" stroke="{accent}" stroke-width="{n(_SW)}" '
            f'stroke-linecap="round" stroke-linejoin="miter"/>'
        )
    # round (default): 'C' / '(' — rounded left corners, short arms, open right
    # (arc sweep-flag 0 traces the correct quarter-circle corners).
    d = (
        f"M {n(_X0 + _ARM)} {n(_Y0)} H {n(_X0 + _R)} "
        f"A {n(_R)} {n(_R)} 0 0 0 {n(_X0)} {n(_Y0 + _R)} "
        f"V {n(y1 - _R)} "
        f"A {n(_R)} {n(_R)} 0 0 0 {n(_X0 + _R)} {n(y1)} H {n(_X0 + _ARM)}"
    )
    return (
        f'<path d="{d}" fill="none" stroke="{accent}" stroke-width="{n(_SW)}" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
    )


class _EsignSignature:
    META = StyleMeta(
        id="esign.signature",
        country="esign",
        shape="overlay",
        title="Signature graphic",
        description=(
            "Typed or scanned signature with clean, classic bracketed, and "
            "signature-only layouts. Removes white paper from scans. "
            "The optional content ID identifies the graphic; it is not a "
            "cryptographic PDF signature, timestamp or proof of identity."
        ),
        canonical_size_mm=(60.0, 60.0 * _H / _W),
        reference=(
            "DocuSign 'Signed by' adopted-signature stamp anatomy; white-knockout "
            "+ embedded <image> data-URI rasterized by resvg."
        ),
    )

    PARAMS = [
        ParamSpec("layout", str, "classic", "Composition: clean with a printed name, classic with brackets, or signature-only.",
                  enum=["clean", "classic", "signature-only"]),
        ParamSpec("show_id", bool, True, "Show the graphic fingerprint (not a signing certificate)."),
        ParamSpec("show_name", bool, True, "Show the printed name in the clean layout."),
        ParamSpec(
            name="signature", type=str, default="sample",
            help="Signature source: a path to an image (PNG/JPG/…) whose white "
                 "background is knocked out and embedded; 'sample' (default) for a "
                 "built-in synthetic demo squiggle (no PII); or 'typed'/'name'/"
                 "'cursive' to render --name in a cursive script font.",
        ),
        ParamSpec(
            name="name", type=str, default="Sample Signer",
            help="Signer's name. Feeds the deterministic ID hash and is the "
                 "cursive content in 'typed' mode (not drawn as its own line — the "
                 "reference anatomy is label / signature / ID).",
        ),
        ParamSpec(
            name="label", type=str, default="Signed by:",
            help="Small bold label at the top of the badge. DocuSign uses "
                 "'Signed by:'. Empty string draws no label.",
        ),
        ParamSpec(
            name="bracket", type=str, default="round",
            enum=list(_BRACKETS),
            help="Bracket drawn in the accent color: 'round' (default, rounded 'C' "
                 "open on the right), 'square' ('[' open on the right), 'full' "
                 "(closed rounded rectangle), or 'none'.",
        ),
        ParamSpec(
            name="color", type=str, default="blue",
            help="Accent color for the bracket, label and ID: a preset (blue, red, "
                 "purple, black, navy, vermilion…) or #RRGGBB. Default 'blue'.",
        ),
        ParamSpec(
            name="sig_color", type=str, default="auto",
            help="Signature ink: 'auto' (default) keeps the image's own ink; "
                 "'match' recolors it to the accent --color (mono look); or any "
                 "preset/#RRGGBB to recolor.",
        ),
        ParamSpec(
            name="sig_id", type=str, default="auto",
            help="Unique ID shown at the bottom. 'auto' (default) computes a "
                 "deterministic SHA-256 content hash (32 uppercase hex). A 32-hex "
                 "value (dashes/spaces ok) is used verbatim; anything else is "
                 "hashed to a stable 32-hex.",
        ),
        ParamSpec(
            name="font", type=str, default="helvetica",
            help="Sans font alias for the label and ID (default Helvetica; also "
                 "arial, or an absolute .ttf/.ttc path).",
        ),
        ParamSpec(
            name="script_font", type=str, default="script",
            help="Cursive font alias used ONLY in 'typed' mode (default 'script' → "
                 "Snell Roundhand on macOS; never resolved on the image/sample "
                 "path).",
        ),
        ParamSpec(
            name="low", type=int, default=110,
            help="White-knockout lower luminance threshold: pixels with L≤low "
                 "become fully opaque ink (0–255).",
        ),
        ParamSpec(
            name="high", type=int, default=245,
            help="White-knockout upper luminance threshold: pixels with L≥high "
                 "become fully transparent, with a linear ramp between low and "
                 "high to preserve anti-aliased edges (0–255).",
        ),
        ParamSpec(
            name="max_px", type=int, default=1600,
            help="Down-scale guard: if the input's long edge exceeds this it is "
                 "LANCZOS-resized before processing (bounds base64 size). Small "
                 "images are never upscaled.",
        ),
    ]

    DEFAULTS = {
        "layout": "classic", "show_id": True, "show_name": True,
        "signature": "sample", "name": "Sample Signer", "label": "Signed by:",
        "bracket": "round", "color": "blue", "sig_color": "auto", "sig_id": "auto",
        "font": "helvetica", "script_font": "script", "low": 110, "high": 245,
        "max_px": 1600,
    }

    def build_svg(self, **params) -> StyleResult:
        n = svg.num
        p = {**self.DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
        warnings: list[str] = []

        name = str(p["name"]).strip()
        name = " ".join(unicodedata.normalize("NFC", name).split())
        label = str(p["label"])
        layout = str(p["layout"])
        if layout not in ("classic", "clean", "signature-only"):
            raise ValueError("Choose layout clean, classic, or signature-only.")
        if len(name) > 160 or len(label) > 160:
            raise ValueError("Name and label must each be at most 160 characters.")
        if not name and str(p["signature"]).lower() in _TYPED_TOKENS:
            raise ValueError("A typed signature needs a non-empty --name.")
        band = ((_BAND_X, _BAND_Y, _BAND_W, _BAND_H) if layout == "classic"
                else ((18, 12, 384, 116) if layout == "signature-only" else (18, 44, 384, 92)))
        if layout == 'classic' and not p['show_id']:
            # Reclaim the hidden reference zone and rebalance the visible ink.
            band = (*band[:3], 128.)
        extra_height = 0.
        accent = colors_mod.parse(str(p["color"]))

        try:
            low = max(0, min(255, int(p["low"])))
            high = max(0, min(255, int(p["high"])))
        except (TypeError, ValueError):
            raise ValueError(f"--low/--high must be integers, got {p['low']!r}/{p['high']!r}")
        if low >= high:
            warnings.append(f"low ({low}) ≥ high ({high}); reset to 110/245.")
            low, high = 110, 245
        try:
            max_px = int(p["max_px"])
            if not 64 <= max_px <= 4096:
                raise ValueError("--max-px must be between 64 and 4096.")
        except (TypeError, ValueError):
            raise ValueError(f"--max-px must be an integer, got {p['max_px']!r}")

        # ── Sans font for label + ID. If the default alias is missing on this
        # host, fall back to any other Latin face (never a network fetch); if
        # none resolve, fail fast (FontMissingError → exit 2), like western.text.
        # An explicit non-default font that fails re-raises directly.
        font_alias = str(p["font"])
        prof = default_resolver.try_resolve(font_alias)
        if prof is None:
            if font_alias.strip().lower() == self.DEFAULTS["font"]:
                prof = default_resolver.first_available(LATIN_ALIASES)
                if prof is None:
                    raise FontMissingError(
                        "no sans font available (tried "
                        f"{', '.join(LATIN_ALIASES)}). Install one or pass --font <path>."
                    )
                warnings.append(f"sans font 'helvetica' unavailable; using {prof.family}.")
            else:
                prof = default_resolver.resolve(font_alias)
        sans_family = prof.family
        fonts_used = [prof]

        # ── Mode.
        sv = str(p["signature"]).strip()
        lk = sv.lower()
        if lk in _SAMPLE_TOKENS:
            mode = "sample"
        elif lk in _TYPED_TOKENS:
            mode = "typed"
        else:
            mode = "image"

        # ── Signature ink (recolor target).
        sc = str(p["sig_color"]).strip().lower()
        if sc == "auto":
            recolor_rgb = None
        elif sc == "match":
            recolor_rgb = colors_mod.parse_rgb(str(p["color"]))
        else:
            recolor_rgb = colors_mod.parse_rgb(str(p["sig_color"]))

        # ── Signature element + the bytes that bind the unique ID.
        image_px: tuple[int, int] | None = None
        script_family: str | None = None
        if mode in ("sample", "image"):
            if mode == "sample":
                pil = _make_sample_image()
            else:
                try:
                    img_path = Path(sv).expanduser()
                except RuntimeError as e:  # e.g. ~unknownuser with no home dir
                    raise ValueError(f"could not resolve signature path {sv!r}: {e}") from e
                pil = _open_image(img_path)
            res = _process_image(
                pil, low=low, high=high, recolor_rgb=recolor_rgb,
                max_px=max_px, warnings=warnings,
            )
            if res is None:
                raise ValueError("signature image is blank after white-knockout.")
            png_bytes, image_px, content_tag = res
            # All layouts expand for a taller mark. Preserve aspect ratio and
            # cap the height so a portrait scan cannot create an enormous page.
            ink_height = max(band[3], min(240., band[2] * image_px[1] / image_px[0]))
            extra_height = ink_height - band[3]
            band = (*band[:3], ink_height)
            if max(image_px) < 300:
                warnings.append("Small signature image; a higher-resolution scan will print more sharply.")
            b64 = base64.b64encode(png_bytes).decode("ascii")
            sig_el = (
                f'<image x="{n(band[0])}" y="{n(band[1])}" width="{n(band[2])}" '
                f'height="{n(band[3])}" preserveAspectRatio="xMidYMid meet" '
                f'xlink:href="data:image/png;base64,{b64}"/>'
            )
        else:  # typed
            sp = default_resolver.resolve(str(p["script_font"]))
            fonts_used.append(sp)
            script_family = sp.family
            ink = accent if sc in ("auto", "match") else colors_mod.parse(str(p["sig_color"]))
            signature_fonts = [sp]
            if _has_non_latin(name):
                fallback = default_resolver.first_available(("song", "hei", "ping", "hiragino"))
                if fallback:
                    signature_fonts.append(fallback)
                    fonts_used.append(fallback)
            sig_el, fs = fitted_text(name, signature_fonts, band, size=72, minimum=18,
                                     color=ink, align="center" if layout == "classic" else "left")
            if fs < 32:
                warnings.append("Long name: signature lettering reduced to fit; check the preview at print size.")
            # Bind the ID to the rendered appearance (font + ink), not just the
            # name, so a different cursive face or color yields a different ID.
            content_tag = (
                b"TYPED:" + f"{sp.family}\x1f{ink}\x1f{fs}\x1f".encode("utf-8")
                + unicodedata.normalize("NFC", name).encode("utf-8")
            )

        # ── CJK fallback. The label (all modes) and the typed name are arbitrary
        # text rendered by the pinned Latin faces; under skip_system_fonts a
        # non-Latin glyph would render as tofu. Pin a CJK face so resvg can
        # glyph-fall-back across font_files (same trick western.text/hk.oval use).
        # Conditional, so the common ASCII path stays lean and dependency-free.
        need_cjk = ((layout != 'signature-only' and _has_non_latin(label))
                    or ((mode == 'typed' or (layout == 'clean' and p['show_name']))
                        and _has_non_latin(name)))
        if need_cjk:
            cjk_prof = default_resolver.first_available(("song", "hei", "ping", "hiragino"))
            if cjk_prof is None:
                warnings.append(
                    "non-Latin text present but no CJK fallback font available; "
                    "glyphs may render as boxes."
                )
            elif cjk_prof.family not in {f.family for f in fonts_used}:
                fonts_used.append(cjk_prof)

        sig_id = _resolve_id(p["sig_id"], name, content_tag, warnings)

        bracket = str(p["bracket"]).strip().lower()
        if bracket not in _BRACKETS:
            raise ValueError(
                f"unknown bracket {bracket!r}; choose one of: {', '.join(_BRACKETS)}."
            )
        bracket_svg = _bracket(bracket, accent, extra_height)

        label_svg = id_svg = ''
        if layout == 'classic':
            label_svg, _ = fitted_text(label, fonts_used,
                                       (_CONTENT_X, 21, _CONTENT_W, 21),
                                       size=18, minimum=11, color=accent)
            if p['show_id']:
                id_svg, _ = fitted_text(sig_id, [prof],
                                        (_CONTENT_X, 161 + extra_height, _CONTENT_W, 29),
                                        size=20, minimum=17, color=accent)
        view_box = (0., 0., _W, _H + extra_height)
        physical_size = (60.0, 60.0 * view_box[3] / _W)
        if layout == "clean":
            bracket_svg = ""
            # Expanded scans fill their band vertically; keep the divider as
            # far from the ink as the top label, rather than crowding the tail.
            footer_shift = extra_height + (12 if extra_height else 0)
            view_box = (0., 0., _W, _H + footer_shift)
            label_svg, _ = fitted_text(label, fonts_used, (18, 10, 384, 23), size=15,
                                       minimum=11, color=accent)
            printed, _ = fitted_text(name if p["show_name"] else "", fonts_used,
                                     (18, 151 + footer_shift, 384, 22), size=18, minimum=14, color=accent)
            rule = f'<path d="M 18 {n(141 + footer_shift)} H 402" stroke="#B9BDC0" stroke-width="0.7"/>' if p["show_name"] else ""
            label_svg += rule + printed
            id_svg, _ = fitted_text(sig_id if p["show_id"] else "", [prof],
                                    (18, 181 + footer_shift, 384, 12), size=10, minimum=9, color=accent)
            physical_size = (70.0, 70.0 * view_box[3] / _W)
        elif layout == "signature-only":
            bracket_svg = label_svg = id_svg = ""
            view_box = (0., 0., _W, 140. + extra_height)
            physical_size = (60., 60. * view_box[3] / _W)

        svg_doc = (
            svg.svg_root(width=view_box[2], height=view_box[3], view_box_tuple=view_box)
            + bracket_svg + label_svg + sig_el + id_svg + "</svg>"
        )

        normalized = {
            "layout": layout,
            "show_id": bool(p["show_id"]) and layout != "signature-only",
            "show_name": bool(p["show_name"]) and layout == "clean",
            "signature_mode": mode,
            "name": name,
            "label": label,
            "bracket": bracket if layout == "classic" else "none",
            "color": accent,
            "sig_color": (
                "auto" if sc == "auto"
                else ("match" if sc == "match" else colors_mod.parse(str(p["sig_color"])))
            ),
            "sig_id": sig_id,
            "font": sans_family,
            "script_font": script_family,
            "low": low,
            "high": high,
            "max_px": max_px,
            "image_px": list(image_px) if image_px else None,
        }

        # The painted area spans from the bracket's left edge (when present) to
        # the content's right edge; content overflows the short bracket arms.
        left = (_X0 - _SW / 2) if bracket != "none" else _CONTENT_X
        right = _X1 if bracket == "full" else _CONTENT_RIGHT
        painted = (left, _Y0 - _SW / 2, right - left, (_Y1 - _Y0) + _SW + extra_height)

        return StyleResult(
            svg=svg_doc,
            normalized_params=normalized,
            warnings=warnings,
            fonts_used=fonts_used,
            view_box=view_box,
            painted_bbox=painted if layout == "classic" else (18., 10., 384., view_box[3] - 20),
            canonical_size_mm=physical_size,
            style_id="esign.signature",
            style_version=_VERSION,
        )


STYLE = _EsignSignature()

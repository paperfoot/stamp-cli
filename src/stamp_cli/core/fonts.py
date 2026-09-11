"""Font discovery for stamp rendering — pinned, deterministic, agent-inspectable.

The render path feeds ``resvg_py`` an explicit list of ``font_files`` and (for
production) ``skip_system_fonts=True``. That kills the entire "wrong font / wrong
weight / works-on-my-machine" class of bugs: every style declares the CSS family
name it puts in the SVG, and the resolver maps that to a concrete file on disk
whose sha256 is surfaced in ``agent-info`` and golden tests.

What lives here:

  * :class:`FontProfile` — one resolved font (family, path, sha256, capabilities).
  * :class:`FontResolver` — discovers system CJK (PingFang / Songti / Hiragino)
    and Latin (Times / Helvetica / Arial) faces, plus the bundled / fetchable
    **Noto Sans Symbols** (OFL) which carries ``❋`` U+274B *and* Latin — the font
    STAMP4U calls ``font1`` and the reason its default English + bottom floret
    share one family.

The alias→candidate-path tables are ported from the original ``fonts.py`` and
extended with the families the new styles need.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# Glyphs we care about probing for. ❋ (U+274B) is STAMP4U's oval bottom mark;
# ★ (U+2605) is the PRC five-pointed star.
PROBE_GLYPHS = ("❋", "★")  # ❋ ★

# OFL Noto Sans Symbols — the STAMP4U `font1` default. Mirrors that ship the
# static (non-variable) TTF; the variable font we already have in spike/ also
# works. Used only as a last resort if no copy is found locally.
NOTO_SYMBOLS_URL = (
    "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/"
    "NotoSansSymbols/NotoSansSymbols-Regular.ttf"
)
NOTO_SYMBOLS_FAMILY = "Noto Sans Symbols"

# Noto Sans Symbols **2** (OFL) — carries the dingbat range incl. ❋ U+274B and
# ★ U+2605 that the plain "Symbols" font lacks. resvg won't *select* it as a
# primary family, but it shapes those glyphs correctly as a glyph-level
# **fallback** when listed alongside a Latin face under skip_system_fonts. So
# styles name ``Noto Sans Symbols`` (Latin) and pin this too for the floret.
NOTO_SYMBOLS2_URL = (
    "https://notofonts.github.io/symbols/fonts/NotoSansSymbols2/hinted/ttf/"
    "NotoSansSymbols2-Regular.ttf"
)
NOTO_SYMBOLS2_FAMILY = "Noto Sans Symbols 2"


@dataclass(frozen=True)
class FontProfile:
    """A resolved, pinned font.

    ``family`` is the CSS ``font-family`` name a style writes into its SVG.
    ``file_path`` is fed verbatim to ``resvg_py(font_files=[...])``. ``sha256``
    makes the choice reproducible and is exposed in agent-info / golden tests.
    """

    family: str
    file_path: str
    sha256: str
    supports_cjk: bool
    supports_latin: bool
    supports_glyph: dict[str, bool] = field(default_factory=dict)
    weight_axis: int | None = None
    face_index: int = 0

    def to_dict(self) -> dict:
        return {
            "family": self.family,
            "file_path": self.file_path,
            "sha256": self.sha256,
            "supports_cjk": self.supports_cjk,
            "supports_latin": self.supports_latin,
            "supports_glyph": {k: v for k, v in self.supports_glyph.items()},
            "weight_axis": self.weight_axis,
            "face_index": self.face_index,
        }


# ── Alias → (path, ttc-index, css-family) candidates ──────────────────────────
# Ported from the original fonts.py and extended. css_family is the name a style
# should reference; we pick the first candidate that exists on disk. ``cjk`` /
# ``latin`` flag what the face can render so probing is cheap and offline.
@dataclass(frozen=True)
class _Candidate:
    path: str
    index: int
    css_family: str
    cjk: bool
    latin: bool


_HOME = str(Path.home())

# Each alias lists candidates best-first. macOS first (dev box), then Linux.
_MAC: dict[str, list[_Candidate]] = {
    "sans": [
        _Candidate("/System/Library/Fonts/Supplemental/Arial.ttf", 0, "Arial", False, True),
    ],
    # CJK serif (Song / Ming) — classic seal face; STAMP4U `sung`/`font5` analog
    "song": [
        _Candidate("/System/Library/Fonts/Supplemental/Songti.ttc", 6, "Songti SC", True, True),
        _Candidate("/System/Library/Fonts/Supplemental/Songti.ttc", 0, "Songti SC", True, True),
    ],
    # CJK sans (Hei) — STAMP4U `black` analog
    "hei": [
        _Candidate("/System/Library/Fonts/STHeiti Medium.ttc", 0, "Heiti SC", True, True),
        _Candidate("/System/Library/Fonts/STHeiti Light.ttc", 0, "Heiti SC", True, True),
    ],
    # PingFang — Apple's default CJK sans (likely the reference browser fallback)
    "ping": [
        _Candidate(f"{_HOME}/Library/Fonts/PingFang Bold.ttf", 0, "PingFang SC", True, True),
        _Candidate(f"{_HOME}/Library/Fonts/PingFang Medium.ttf", 0, "PingFang SC", True, True),
        _Candidate("/System/Library/Fonts/PingFang.ttc", 0, "PingFang SC", True, True),
    ],
    # Hiragino — fallback CJK sans
    "hiragino": [
        _Candidate("/System/Library/Fonts/Hiragino Sans GB.ttc", 1, "Hiragino Sans GB", True, True),
        _Candidate("/System/Library/Fonts/Hiragino Sans GB.ttc", 0, "Hiragino Sans GB", True, True),
    ],
    # Kai (regular script) — STAMP4U `font3`/kaiu analog; degrade to Song
    "kai": [
        _Candidate("/System/Library/Fonts/Supplemental/STKaiti.ttc", 0, "Kaiti SC", True, True),
        _Candidate("/System/Library/Fonts/Supplemental/Kaiti.ttc", 0, "Kaiti SC", True, True),
        _Candidate("/System/Library/Fonts/Supplemental/Songti.ttc", 6, "Songti SC", True, True),
    ],
    # Latin
    "times": [
        _Candidate("/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf", 0, "Times New Roman", False, True),
        _Candidate("/System/Library/Fonts/Supplemental/Times New Roman.ttf", 0, "Times New Roman", False, True),
    ],
    "arial": [
        _Candidate("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0, "Arial", False, True),
        _Candidate("/System/Library/Fonts/Supplemental/Arial.ttf", 0, "Arial", False, True),
        _Candidate("/Library/Fonts/Arial.ttf", 0, "Arial", False, True),
    ],
    "helvetica": [
        _Candidate("/System/Library/Fonts/Helvetica.ttc", 1, "Helvetica", False, True),
        _Candidate("/System/Library/Fonts/Helvetica.ttc", 0, "Helvetica", False, True),
    ],
    # Cursive / handwriting — used for the e-signature "typed signature" mode.
    # Snell Roundhand is the closest macOS analog to the DocuSign adopted-cursive
    # look; Brush Script / Apple Chancery are graceful alternates.
    "script": [
        _Candidate("/System/Library/Fonts/Supplemental/SnellRoundhand.ttc", 0, "Snell Roundhand", False, True),
        _Candidate("/System/Library/Fonts/Supplemental/Brush Script.ttf", 0, "Brush Script MT", False, True),
        _Candidate("/System/Library/Fonts/Supplemental/Apple Chancery.ttf", 0, "Apple Chancery", False, True),
    ],
}

_LINUX: dict[str, list[_Candidate]] = {
    "sans": [
        _Candidate("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf", 0, "Liberation Sans", False, True),
        _Candidate("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 0, "Liberation Sans", False, True),
        _Candidate("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0, "DejaVu Sans", False, True),
    ],
    "song": [
        _Candidate("/usr/share/fonts/truetype/arphic/uming.ttc", 0, "AR PL UMing CN", True, True),
        _Candidate("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", 2, "Noto Serif CJK SC", True, True),
    ],
    "hei": [
        _Candidate("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 2, "Noto Sans CJK SC", True, True),
        _Candidate("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0, "WenQuanYi Micro Hei", True, True),
    ],
    "ping": [
        _Candidate("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 2, "Noto Sans CJK SC", True, True),
    ],
    "kai": [
        _Candidate("/usr/share/fonts/truetype/arphic/ukai.ttc", 0, "AR PL UKai CN", True, True),
    ],
    "times": [
        _Candidate("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf", 0, "Liberation Serif", False, True),
    ],
    "arial": [
        _Candidate("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0, "Liberation Sans", False, True),
        _Candidate("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0, "DejaVu Sans", False, True),
    ],
    "helvetica": [
        _Candidate("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0, "Liberation Sans", False, True),
    ],
    # Cursive fallback on Linux: the common OFL handwriting packages if present.
    "script": [
        _Candidate("/usr/share/fonts/truetype/dancing-script/DancingScript-Regular.ttf", 0, "Dancing Script", False, True),
        _Candidate("/usr/share/fonts/truetype/tinos/Tinos-Italic.ttf", 0, "Tinos", False, True),
        _Candidate("/usr/share/fonts/truetype/liberation2/LiberationSerif-Italic.ttf", 0, "Liberation Serif", False, True),
        _Candidate("/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf", 0, "Liberation Serif", False, True),
    ],
}

# Canonical alias groups used by doctor / discovery.
CJK_ALIASES = ("ping", "song", "hei", "hiragino", "kai")
LATIN_ALIASES = ("sans", "times", "arial", "helvetica")
ALIASES = sorted(set(_MAC) | set(_LINUX) | {"symbols", "symbols2"})

# Where a fetched Noto Sans Symbols is cached.
_CACHE_DIR = Path(
    os.environ.get("STAMP_CLI_FONT_CACHE", str(Path.home() / ".cache" / "stamp-cli" / "fonts"))
)

# Bundled symbols font that ships with the repo spike (fastest path).
_BUNDLED_SYMBOLS = [
    Path(__file__).resolve().parents[3] / "spike" / "fonts" / "NotoSansSymbols.ttf",
    _CACHE_DIR / "NotoSansSymbols.ttf",
]

# Bundled Noto Sans Symbols 2 (the ❋ / ★ dingbat provider; see above).
_BUNDLED_SYMBOLS2 = [
    Path(__file__).resolve().parents[3] / "spike" / "fonts" / "NotoSansSymbols2.ttf",
    _CACHE_DIR / "NotoSansSymbols2.ttf",
]


def _is_mac() -> bool:
    return sys.platform == "darwin"


@lru_cache(maxsize=256)
def _sha256_for_stat(path: str, mtime_ns: int, size: int) -> str:
    """Hash one immutable view of a font file.

    ``mtime_ns`` and ``size`` are deliberately part of the cache key. Aliases
    that select different faces from the same TTC therefore share one file
    read, while an updated font file is rehashed within the same process.
    """
    del mtime_ns, size
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256(path: str) -> str:
    stat = os.stat(path)
    return _sha256_for_stat(path, stat.st_mtime_ns, stat.st_size)


def _probe_glyphs(path: str, index: int = 0) -> dict[str, bool]:
    """Return ``{glyph: present}`` for :data:`PROBE_GLYPHS`.

    Uses fontTools if available (accurate, reads the cmap). Falls back to an
    empty/unknown map (all False) when fontTools is absent so discovery never
    crashes — callers treat False conservatively.
    """
    try:
        from fontTools.ttLib import TTFont, TTCollection  # type: ignore
    except Exception:
        return {g: False for g in PROBE_GLYPHS}
    collection = None
    font = None
    try:
        if path.lower().endswith(".ttc"):
            collection = TTCollection(path, lazy=True)
            font = collection.fonts[index if index < len(collection.fonts) else 0]
        else:
            font = TTFont(path, lazy=True, fontNumber=index if index else 0)
        cmap = font.getBestCmap() or {}
        return {g: (ord(g) in cmap) for g in PROBE_GLYPHS}
    except Exception:
        return {g: False for g in PROBE_GLYPHS}
    finally:
        if collection is not None:
            collection.close()
        elif font is not None:
            font.close()


def _family_from_file(path: str, index: int = 0) -> str | None:
    """Best OpenType family name from a font file (nameID 16, then nameID 1).

    resvg matches glyph runs against this internal family name under
    ``skip_system_fonts=True``, so the file *stem* (e.g. ``SnellRoundhand``) is
    NOT a safe substitute for the real family (``Snell Roundhand``) — using the
    stem makes the text render as nothing. Returns ``None`` when fontTools is
    unavailable or the name can't be read, so callers fall back to the stem.
    """
    try:
        from fontTools.ttLib import TTFont, TTCollection  # type: ignore
    except Exception:
        return None
    collection = None
    font = None
    try:
        if path.lower().endswith(".ttc"):
            collection = TTCollection(path, lazy=True)
            font = collection.fonts[index if index < len(collection.fonts) else 0]
        else:
            font = TTFont(path, lazy=True, fontNumber=index if index else 0)
        name = font["name"]
        # nameID 16 = Typographic Family (preferred); 1 = legacy Family.
        fam = name.getDebugName(16) or name.getDebugName(1)
        return fam or None
    except Exception:
        return None
    finally:
        if collection is not None:
            collection.close()
        elif font is not None:
            font.close()


class FontMissingError(RuntimeError):
    """Raised when a required font family/alias cannot be resolved on this host.

    The CLI maps this to exit code 2 (font/runtime missing).
    """


class FontResolver:
    """Resolve aliases / CSS families to pinned :class:`FontProfile` objects.

    Results are cached per-process so sha256 is hashed once. ``allow_fetch``
    controls whether :meth:`symbols` may download the OFL Noto Sans Symbols when
    no local copy exists.
    """

    def __init__(self, *, allow_fetch: bool = True) -> None:
        self.allow_fetch = allow_fetch
        self._cache: dict[str, FontProfile] = {}

    # -- discovery -------------------------------------------------------------
    def _candidates(self, alias: str) -> list[_Candidate]:
        table = _MAC if _is_mac() else _LINUX
        # Always allow the *other* table as a secondary source so a mac path on
        # Linux (or vice versa) still has a shot via fc-match below.
        return table.get(alias, [])

    def _build_profile(self, cand: _Candidate) -> FontProfile:
        glyphs = _probe_glyphs(cand.path, cand.index)
        return FontProfile(
            family=cand.css_family,
            file_path=cand.path,
            sha256=_sha256(cand.path),
            supports_cjk=cand.cjk,
            supports_latin=cand.latin,
            supports_glyph=glyphs,
            weight_axis=None,
            face_index=cand.index,
        )

    def _profile_from_path(self, path: str, *, family: str | None = None,
                         cjk: bool, latin: bool) -> FontProfile:
        glyphs = _probe_glyphs(path)
        return FontProfile(
            family=family or _family_from_file(path) or Path(path).stem,
            file_path=path,
            sha256=_sha256(path),
            supports_cjk=cjk,
            supports_latin=latin,
            supports_glyph=glyphs,
        )

    def resolve(self, name_or_path: str) -> FontProfile:
        """Resolve an alias (``song``, ``times``, ``symbols`` …) or a file path.

        Order: cache → bundled symbols (for ``symbols``) → alias candidate table
        → direct file path → ``fc-match``. Raises :class:`FontMissingError` if
        nothing usable is found.
        """
        key = name_or_path.strip()
        if key in self._cache:
            return self._cache[key]

        lk = key.lower()
        if lk in ("symbols", "noto", "noto-symbols", "font1", "default"):
            prof = self.symbols()
            self._cache[key] = prof
            return prof
        if lk in ("symbols2", "noto-symbols2", "dingbats", "floret"):
            prof = self.symbols2()
            self._cache[key] = prof
            return prof

        # Direct filesystem path.
        if os.path.sep in key or key.endswith((".ttf", ".ttc", ".otf")):
            p = Path(key).expanduser()
            if p.is_file():
                # Heuristic capabilities for an arbitrary file: assume both.
                prof = self._profile_from_path(str(p), cjk=True, latin=True)
                self._cache[key] = prof
                return prof
            raise FontMissingError(f"Font file not found: {p}")

        # Alias candidate table.
        for cand in self._candidates(lk):
            if Path(cand.path).is_file():
                prof = self._build_profile(cand)
                self._cache[key] = prof
                return prof

        # fc-match fallback (Linux / fontconfig hosts).
        path = self._fc_match(lk)
        if path:
            prof = self._profile_from_path(path, cjk=lk in CJK_ALIASES, latin=True)
            self._cache[key] = prof
            return prof

        raise FontMissingError(
            f"Could not resolve font '{name_or_path}'. Known aliases: "
            f"{', '.join(ALIASES)}. Or pass an absolute .ttf/.ttc/.otf path."
        )

    def _fc_match(self, query: str) -> str | None:
        fc = shutil.which("fc-match")
        if not fc:
            return None
        try:
            out = subprocess.check_output(
                [fc, "-f", "%{file}", query],
                stderr=subprocess.DEVNULL, text=True, timeout=3,
            ).strip()
            if out and Path(out).is_file():
                return out
        except (subprocess.SubprocessError, OSError):
            pass
        return None

    # -- the special symbols font ---------------------------------------------
    def symbols(self) -> FontProfile:
        """Resolve **Noto Sans Symbols** (STAMP4U ``font1``; Latin + weights).

        This is the OFL face styles name for default English text. Note the
        widely-mirrored "Symbols" build is a subset that does **not** include the
        ``❋`` U+274B floret — pair it with :meth:`symbols2` (Noto Sans Symbols 2)
        in ``fonts_used`` so resvg can shape the floret via glyph fallback.

        Tries bundled / cached copies first, then downloads the OFL font to the
        cache when ``allow_fetch`` is set. Raises :class:`FontMissingError` if no
        copy is available and fetching is disabled or fails.
        """
        if "__symbols__" in self._cache:
            return self._cache["__symbols__"]

        for p in _BUNDLED_SYMBOLS:
            if p.is_file():
                prof = self._profile_from_path(
                    str(p), family=NOTO_SYMBOLS_FAMILY, cjk=False, latin=True
                )
                self._cache["__symbols__"] = prof
                return prof

        if not self.allow_fetch:
            raise FontMissingError(
                "Noto Sans Symbols not found and fetching is disabled. "
                "Place NotoSansSymbols.ttf in spike/fonts/ or "
                f"{_CACHE_DIR}, or run `stamp fonts --fetch`."
            )

        dest = _CACHE_DIR / "NotoSansSymbols.ttf"
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(NOTO_SYMBOLS_URL, dest)  # noqa: S310
        except Exception as e:  # network / write failure
            raise FontMissingError(
                f"Failed to fetch Noto Sans Symbols (OFL) from {NOTO_SYMBOLS_URL}: {e}"
            ) from e
        prof = self._profile_from_path(
            str(dest), family=NOTO_SYMBOLS_FAMILY, cjk=False, latin=True
        )
        self._cache["__symbols__"] = prof
        return prof

    def symbols2(self) -> FontProfile:
        """Resolve **Noto Sans Symbols 2** — the ``❋`` / ``★`` dingbat provider.

        resvg won't pick this as a primary ``font-family`` match, but listing it
        in ``font_files`` lets resvg fall back to it for the floret/star glyphs
        the plain Symbols font lacks — deterministically, even under
        ``skip_system_fonts=True``. Bundled-first, then fetched to cache.
        """
        if "__symbols2__" in self._cache:
            return self._cache["__symbols2__"]

        for p in _BUNDLED_SYMBOLS2:
            if p.is_file():
                prof = self._profile_from_path(
                    str(p), family=NOTO_SYMBOLS2_FAMILY, cjk=False, latin=False
                )
                self._cache["__symbols2__"] = prof
                return prof

        if not self.allow_fetch:
            raise FontMissingError(
                "Noto Sans Symbols 2 not found and fetching is disabled. "
                "Place NotoSansSymbols2.ttf in spike/fonts/ or "
                f"{_CACHE_DIR}, or run `stamp fonts --fetch`."
            )

        dest = _CACHE_DIR / "NotoSansSymbols2.ttf"
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(NOTO_SYMBOLS2_URL, dest)  # noqa: S310
        except Exception as e:  # network / write failure
            raise FontMissingError(
                f"Failed to fetch Noto Sans Symbols 2 (OFL) from {NOTO_SYMBOLS2_URL}: {e}"
            ) from e
        prof = self._profile_from_path(
            str(dest), family=NOTO_SYMBOLS2_FAMILY, cjk=False, latin=False
        )
        self._cache["__symbols2__"] = prof
        return prof

    # -- introspection ---------------------------------------------------------
    def try_resolve(self, alias: str) -> FontProfile | None:
        """Resolve or return ``None`` (never raises) — for doctor / listings."""
        try:
            return self.resolve(alias)
        except FontMissingError:
            return None

    def first_available(self, aliases: tuple[str, ...]) -> FontProfile | None:
        """Return the first alias in ``aliases`` that resolves, else ``None``."""
        for a in aliases:
            prof = self.try_resolve(a)
            if prof is not None:
                return prof
        return None

    def listing(self) -> list[tuple[str, str | None, bool, bool]]:
        """``[(alias, path_or_None, cjk, latin)]`` across all known aliases."""
        rows: list[tuple[str, str | None, bool, bool]] = []
        for alias in ALIASES:
            prof = self.try_resolve(alias)
            if prof:
                rows.append((alias, prof.file_path, prof.supports_cjk, prof.supports_latin))
            else:
                rows.append((alias, None, alias in CJK_ALIASES, alias in LATIN_ALIASES))
        return rows


# Module-level default resolver (fetch allowed). Styles/CLI share this.
default_resolver = FontResolver(allow_fetch=True)

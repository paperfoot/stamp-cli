"""Focused tests for deterministic font profile metadata and hashing."""

from __future__ import annotations

import builtins
import os

from stamp_cli.core import fonts


def test_candidate_ttc_face_index_is_preserved(monkeypatch, tmp_path):
    font_path = tmp_path / "Example.ttc"
    font_path.write_bytes(b"synthetic-font")
    monkeypatch.setattr(fonts, "_probe_glyphs", lambda path, index=0: {})
    monkeypatch.setattr(fonts, "_sha256", lambda path: "0" * 64)

    candidate = fonts._Candidate(
        str(font_path), 6, "Example Family", cjk=True, latin=True
    )
    profile = fonts.FontResolver(allow_fetch=False)._build_profile(candidate)

    assert profile.face_index == 6
    assert profile.to_dict()["face_index"] == 6


def test_arbitrary_font_path_defaults_to_first_face(monkeypatch, tmp_path):
    font_path = tmp_path / "Example.ttc"
    font_path.write_bytes(b"synthetic-font")
    monkeypatch.setattr(fonts, "_probe_glyphs", lambda path, index=0: {})
    monkeypatch.setattr(fonts, "_family_from_file", lambda path, index=0: "Example")
    monkeypatch.setattr(fonts, "_sha256", lambda path: "0" * 64)

    profile = fonts.FontResolver(allow_fetch=False).resolve(str(font_path))

    assert profile.face_index == 0


def test_font_hash_cache_uses_file_stat(monkeypatch, tmp_path):
    font_path = tmp_path / "font.bin"
    font_path.write_bytes(b"alpha")
    fonts._sha256_for_stat.cache_clear()

    real_open = builtins.open
    reads = 0

    def counting_open(*args, **kwargs):
        nonlocal reads
        reads += 1
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", counting_open)
    first = fonts._sha256(str(font_path))
    assert fonts._sha256(str(font_path)) == first
    assert reads == 1

    old_stat = font_path.stat()
    font_path.write_bytes(b"bravo")
    os.utime(
        font_path,
        ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1_000_000_000),
    )

    assert fonts._sha256(str(font_path)) != first
    assert reads == 2

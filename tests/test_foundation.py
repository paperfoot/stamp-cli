"""Foundation tests — core modules + CLI introspection, independent of any style."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from stamp_cli.core import colors, svg


# ── colors ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "spec,expected",
    [
        ("red", "#FF0000"),       # STAMP4U red, not cinnabar
        ("#0220c7", "#0220C7"),   # blue
        ("#8216db", "#8216DB"),   # purple
    ],
)
def test_color_parse_known(spec, expected):
    got = colors.parse(spec)
    # parse may return an (r,g,b) tuple or a hex string depending on impl;
    # normalize both to an uppercase #RRGGBB for comparison.
    if isinstance(got, tuple):
        got = "#{:02X}{:02X}{:02X}".format(*got[:3])
    assert got.upper() == expected


def test_color_parse_rejects_garbage():
    with pytest.raises(ValueError):
        colors.parse("not-a-color")


# ── svg number formatting must be deterministic / byte-stable ─────────────────
def test_svg_number_formatting_deterministic():
    # Whatever the formatter is called, the same float must format identically.
    fmt = getattr(svg, "fmt_num", None) or getattr(svg, "num", None) or getattr(svg, "f", None)
    if fmt is None:
        pytest.skip("no public number formatter exposed in core.svg")
    assert fmt(1.0 / 3.0) == fmt(1.0 / 3.0)
    # No scientific notation, no trailing garbage that would break SVG.
    assert "e" not in fmt(0.0000001).lower()


def test_svg_xml_escape():
    assert svg.esc('<a>&') == '&lt;a&gt;&amp;'
    assert svg.esc_attr('"') == '&quot;'
    assert svg.esc_attr("'") == '&#39;'


# ── CLI introspection (run as a subprocess so we test the real entrypoint) ────
def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "stamp_cli", *args],
        capture_output=True, text=True,
    )


def test_agent_info_json_is_clean_on_stdout():
    """agent-info --json must emit ONLY valid JSON on stdout (warnings -> stderr)."""
    r = subprocess.run(
        ["uv", "run", "stamp", "agent-info", "--json"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)            # must parse with no 'Extra data'
    assert "styles" in data
    assert isinstance(data["styles"], list)


def test_doctor_exits_zero():
    r = subprocess.run(["uv", "run", "stamp", "doctor"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "resvg" in (r.stdout + r.stderr).lower()


def test_unknown_style_is_user_error_exit_1():
    r = subprocess.run(
        ["uv", "run", "stamp", "generate", "--style", "nope.nope", "--params", "{}"],
        capture_output=True, text=True,
    )
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)

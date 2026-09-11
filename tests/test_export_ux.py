"""Regression coverage for safe, predictable export behavior."""

from __future__ import annotations

import importlib
import json
import os
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from click.testing import CliRunner
from PIL import Image

from stamp_cli import styles
from stamp_cli.core import output as output_mod
from stamp_cli.core.raster import RasterizerMissingError


cli_mod = importlib.import_module("stamp_cli.cli")
cli = cli_mod.cli


def _western_args(*extra: str) -> list[str]:
    return ["western", "text", "--preset", "PAID", *extra]


def _json_error(
    runner: CliRunner,
    *,
    style: str,
    params: dict,
) -> tuple[object, dict]:
    result = runner.invoke(
        cli,
        [
            "generate",
            "--style",
            style,
            "--params",
            "-",
            "--stdout",
            "--format",
            "svg",
            "--json",
        ],
        input=json.dumps(params),
    )
    assert result.exit_code == 1
    assert result.stdout_bytes == b""
    return result, json.loads(result.stderr)


def _png_phys(blob: bytes) -> tuple[int, int, int]:
    """Return the PNG pHYs pixels-per-metre pair and unit byte."""
    assert blob.startswith(b"\x89PNG\r\n\x1a\n")
    offset = 8
    while offset < len(blob):
        length = struct.unpack(">I", blob[offset:offset + 4])[0]
        kind = blob[offset + 4:offset + 8]
        data = blob[offset + 8:offset + 8 + length]
        if kind == b"pHYs":
            return (*struct.unpack(">II", data[:8]), data[8])
        offset += 12 + length
    raise AssertionError("PNG has no pHYs print-resolution chunk")


def test_existing_output_is_rejected_before_render_unless_force(tmp_path, monkeypatch):
    target = tmp_path / "paid.svg"
    target.write_bytes(b"previous")
    spec = styles.get("western.text")
    original_build = spec.build_svg
    calls = []

    def tracked_build(**params):
        calls.append(params)
        return original_build(**params)

    monkeypatch.setattr(spec, "build_svg", tracked_build)
    runner = CliRunner()

    refused = runner.invoke(cli, _western_args("-o", str(target)))
    assert refused.exit_code == 1
    assert "already exists" in refused.stderr.lower()
    assert target.read_bytes() == b"previous"
    assert calls == [], "preflight must reject the destination before rendering"

    replaced = runner.invoke(cli, _western_args("-o", str(target), "--force"))
    assert replaced.exit_code == 0, replaced.output
    assert target.read_text(encoding="utf-8").startswith("<svg")
    assert len(calls) == 1


def test_both_formats_render_before_writing_and_preserve_prior_files_on_png_failure(
    tmp_path, monkeypatch
):
    base = tmp_path / "paid"
    svg_path = base.with_suffix(".svg")
    png_path = base.with_suffix(".png")
    svg_path.write_bytes(b"previous svg")
    png_path.write_bytes(b"previous png")

    def fail_png(*args, **kwargs):
        raise RasterizerMissingError("synthetic PNG failure")

    monkeypatch.setattr(cli_mod.raster_mod, "render_png", fail_png)
    result = CliRunner().invoke(
        cli,
        _western_args("-o", str(base), "--format", "both", "--force"),
    )

    assert result.exit_code == 3
    assert "synthetic PNG failure" in result.stderr
    assert svg_path.read_bytes() == b"previous svg"
    assert png_path.read_bytes() == b"previous png"


def test_second_new_file_failure_rolls_back_first(tmp_path, monkeypatch):
    svg_path = tmp_path / "paid.svg"
    png_path = tmp_path / "paid.png"
    real_link = output_mod.os.link

    def fail_second_link(src, dst, *args, **kwargs):
        if Path(dst) == png_path:
            raise OSError("synthetic second-file failure")
        return real_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(output_mod.os, "link", fail_second_link)
    with pytest.raises(output_mod.IOErrorStamp, match="synthetic second-file failure"):
        output_mod.write_artifacts(
            {svg_path: b"new svg", png_path: b"new png"},
            force=False,
        )

    assert not svg_path.exists()
    assert not png_path.exists()
    assert not list(tmp_path.glob(".stamp-*"))


def test_second_forced_file_failure_restores_both_prior_files(tmp_path, monkeypatch):
    svg_path = tmp_path / "paid.svg"
    png_path = tmp_path / "paid.png"
    svg_path.write_bytes(b"previous svg")
    png_path.write_bytes(b"previous png")
    real_replace = output_mod.os.replace

    def fail_second_replace(src, dst, *args, **kwargs):
        if Path(dst) == png_path and Path(src).name.startswith(".stamp-"):
            raise OSError("synthetic second-file failure")
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(output_mod.os, "replace", fail_second_replace)
    with pytest.raises(output_mod.IOErrorStamp, match="synthetic second-file failure"):
        output_mod.write_artifacts(
            {svg_path: b"new svg", png_path: b"new png"},
            force=True,
        )

    assert svg_path.read_bytes() == b"previous svg"
    assert png_path.read_bytes() == b"previous png"
    assert not list(tmp_path.glob(".stamp-*"))


@pytest.mark.parametrize(
    "extra",
    [
        ("--stdout", "--format", "both"),
        ("--stdout", "--format", "svg", "--output", "unused.svg"),
    ],
)
def test_stdout_rejects_multiple_or_file_destinations(extra):
    result = CliRunner().invoke(cli, _western_args(*extra))
    assert result.exit_code == 1
    assert result.stdout_bytes == b""
    assert "--stdout" in result.stderr


def test_stdout_json_error_keeps_stdout_empty_and_stderr_machine_readable():
    result = CliRunner().invoke(
        cli,
        ["generate", "--style", "missing.style", "--stdout", "--json"],
    )
    assert result.exit_code == 1
    assert result.stdout_bytes == b""
    error = json.loads(result.stderr)
    assert error["ok"] is False
    assert error["exit_code"] == 1
    assert "unknown style" in error["error"].lower()


@pytest.mark.parametrize(
    ("style", "params", "message"),
    [
        ("western.text", {"linse": ["PAID"]}, "unknown parameter"),
        ("western.text", {"lines": "PAID"}, "must be list"),
        (
            "prc.contract",
            {"name": "示例科技有限公司", "star_scale": float("nan")},
            "must be finite",
        ),
        ("western.text", {"lines": ["PAID\x01"]}, "invalid xml characters"),
    ],
)
def test_json_params_reject_unknown_types_nan_and_control_characters(
    style, params, message
):
    result, error = _json_error(CliRunner(), style=style, params=params)
    assert error["ok"] is False
    assert error["exit_code"] == 1
    assert message in error["error"].lower()
    assert result.stdout_bytes == b""


def test_size_and_dpi_are_mutually_exclusive(tmp_path):
    result = CliRunner().invoke(
        cli,
        _western_args(
            "--size", "600", "--dpi", "300", "-o", str(tmp_path / "paid.png")
        ),
    )
    assert result.exit_code == 1
    assert "--size" in result.stderr and "--dpi" in result.stderr
    assert not (tmp_path / "paid.png").exists()


def test_seed_requires_weathered(tmp_path):
    result = CliRunner().invoke(
        cli,
        _western_args("--seed", "7", "-o", str(tmp_path / "paid.svg")),
    )
    assert result.exit_code == 1
    assert "--seed requires --weathered" in result.stderr
    assert not (tmp_path / "paid.svg").exists()


def test_svg_has_physical_size_and_requested_background(tmp_path):
    target = tmp_path / "paid.svg"
    result = CliRunner().invoke(
        cli,
        _western_args("--width-mm", "50", "--background", "white", "-o", str(target)),
    )
    assert result.exit_code == 0, result.output

    root = ET.fromstring(target.read_bytes())
    assert root.attrib["width"] == "50mm"
    assert root.attrib["height"].endswith("mm")
    assert float(root.attrib["height"][:-2]) == pytest.approx(
        50 * 200 / 360, abs=0.001
    )
    background = next(child for child in root if not child.tag.endswith("metadata"))
    assert background.tag.endswith("rect")
    assert background.attrib["fill"] == "white"


def test_png_size_aspect_and_print_resolution(tmp_path):
    target = tmp_path / "paid.png"
    result = CliRunner().invoke(
        cli,
        _western_args("--width-mm", "50", "--dpi", "300", "-o", str(target)),
    )
    assert result.exit_code == 0, result.output

    blob = target.read_bytes()
    with Image.open(target) as image:
        assert image.width == 591
        assert image.width / image.height == pytest.approx(360 / 200, abs=0.01)
    # 591 pixels across exactly 50 mm is 11,820 pixels/metre (300.228 DPI).
    assert _png_phys(blob) == (11820, 11820, 1)


def test_weathering_is_seeded_for_svg_and_png(tmp_path):
    outputs = []
    runner = CliRunner()
    for label, seed in (("a", 73), ("b", 73), ("c", 74)):
        base = tmp_path / f"weather-{label}"
        result = runner.invoke(
            cli,
            _western_args(
                "--weathered",
                "--seed",
                str(seed),
                "--size",
                "128",
                "--format",
                "both",
                "-o",
                str(base),
            ),
        )
        assert result.exit_code == 0, result.output
        outputs.append((base.with_suffix(".svg").read_bytes(), base.with_suffix(".png").read_bytes()))

    assert outputs[0][0] == outputs[1][0]
    assert outputs[0][1] == outputs[1][1]
    assert outputs[0][0] != outputs[2][0]
    assert outputs[0][1] != outputs[2][1]

"""Tests for the converter orchestrator."""

import os

from click.testing import CliRunner

from audiobook_binder.cli import cli
from audiobook_binder.converter import determine_bitrate, discover_mp3s


def test_discover_mp3s_natural_sort(sample_mp3s):
    mp3s = discover_mp3s(sample_mp3s)
    filenames = [os.path.basename(p) for p in mp3s]
    assert filenames == ["01_intro.mp3", "02_chapter1.mp3", "03_chapter2.mp3"]


def test_determine_bitrate_clamps():
    class FakeAF:
        def __init__(self, br):
            self.bitrate = br

    assert determine_bitrate([FakeAF(32)]) == 64  # floor
    assert determine_bitrate([FakeAF(128)]) == 128
    assert determine_bitrate([FakeAF(320)]) == 256  # cap
    assert determine_bitrate([FakeAF(64), FakeAF(192)]) == 192  # max


def test_cli_init(sample_mp3s):
    runner = CliRunner()
    result = runner.invoke(cli, ["init", sample_mp3s])
    assert result.exit_code == 0
    assert "Generated" in result.output
    assert os.path.isfile(os.path.join(sample_mp3s, "manifest.yml"))


def test_cli_convert_dry_run(sample_mp3s):
    runner = CliRunner()
    result = runner.invoke(cli, [
        "convert", sample_mp3s,
        "--dry-run",
        "--title", "Test Book",
        "--author", "Test Author",
    ])
    assert result.exit_code == 0
    assert "Dry Run" in result.output
    assert "Test Book" in result.output
    assert "Test Author" in result.output
    assert "Introduction" in result.output


def test_cli_convert_produces_m4b(sample_mp3s):
    output = os.path.join(sample_mp3s, "out.m4b")
    runner = CliRunner()
    result = runner.invoke(cli, [
        "convert", sample_mp3s,
        "-o", output,
        "--title", "Integration Test",
    ])
    assert result.exit_code == 0, result.output
    assert os.path.isfile(output)
    assert os.path.getsize(output) > 0

"""Shared test fixtures."""

from __future__ import annotations

import os
import subprocess
import tempfile

import pytest


@pytest.fixture
def tmp_dir():
    """Create a temporary directory that's cleaned up after the test."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def make_mp3(tmp_dir):
    """Factory fixture that creates short silent MP3 files for testing."""

    def _make(filename: str, duration_s: float = 1.0, title: str | None = None) -> str:
        path = os.path.join(tmp_dir, filename)
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            "anullsrc=r=44100:cl=mono",
            "-t", str(duration_s),
            "-q:a", "9",
            "-map_metadata", "-1",
        ]
        if title:
            cmd.extend(["-metadata", "title={}".format(title)])
        cmd.append(path)
        subprocess.run(cmd, capture_output=True, check=True)
        return path

    return _make


@pytest.fixture
def sample_mp3s(make_mp3, tmp_dir):
    """Create a set of 3 short MP3 files for integration tests."""
    make_mp3("01_intro.mp3", duration_s=1.0, title="Introduction")
    make_mp3("02_chapter1.mp3", duration_s=1.5, title="The Journey Begins")
    make_mp3("03_chapter2.mp3", duration_s=2.0)
    return tmp_dir

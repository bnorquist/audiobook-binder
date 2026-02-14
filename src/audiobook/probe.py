"""ffprobe wrapper for extracting audio file metadata."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

from audiobook.models import AudioFile


def ensure_ffprobe() -> str:
    """Return the path to ffprobe, or raise if not found."""
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError(
            "ffprobe not found on PATH. Install ffmpeg: brew install ffmpeg"
        )
    return path


def probe_file(filepath: str) -> AudioFile:
    """Probe a single MP3 file with ffprobe and return an AudioFile."""
    ffprobe = ensure_ffprobe()
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filepath,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    fmt = data.get("format", {})
    streams = data.get("streams", [])

    # Find the audio stream
    audio_stream = None
    for s in streams:
        if s.get("codec_type") == "audio":
            audio_stream = s
            break

    duration_s = float(fmt.get("duration", 0))
    duration_ms = int(duration_s * 1000)

    # Bitrate: prefer format-level, fall back to stream-level
    bitrate_str = fmt.get("bit_rate") or (audio_stream or {}).get("bit_rate") or "0"
    bitrate_kbps = int(bitrate_str) // 1000

    sample_rate = int((audio_stream or {}).get("sample_rate", 44100))

    # Extract tags from format-level (where ID3 tags usually appear)
    raw_tags = fmt.get("tags", {})
    tags = {k.lower(): v for k, v in raw_tags.items()}

    return AudioFile(
        path=os.path.abspath(filepath),
        filename=os.path.basename(filepath),
        duration_ms=duration_ms,
        bitrate=bitrate_kbps,
        sample_rate=sample_rate,
        tags=tags,
    )


def probe_files(filepaths: list[str], max_workers: int | None = None) -> list[AudioFile]:
    """Probe multiple files in parallel and return a list of AudioFiles.

    Preserves input ordering. Uses threads since the work is subprocess I/O.
    """
    from concurrent.futures import ThreadPoolExecutor

    if max_workers is None:
        max_workers = min(8, len(filepaths))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(probe_file, filepaths))
    return results

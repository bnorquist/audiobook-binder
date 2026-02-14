"""Core conversion orchestrator: MP3s -> M4B."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile

import click
from natsort import natsorted

from audiobook.manifest import (
    find_manifest,
    get_chapter_titles,
    get_file_order,
    get_metadata,
    load_manifest,
)
from audiobook.metadata import (
    build_chapters,
    detect_book_metadata,
    format_duration,
    generate_ffmetadata,
)
from audiobook.models import BookMetadata, Chapter
from audiobook.probe import ensure_ffprobe, probe_files


def ensure_ffmpeg() -> str:
    """Return the path to ffmpeg, or raise if not found."""
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install ffmpeg: brew install ffmpeg"
        )
    return path


def discover_mp3s(input_path: str) -> list[str]:
    """Find all MP3 files in a directory, natural-sorted by filename."""
    if not os.path.isdir(input_path):
        raise click.ClickException("{} is not a directory".format(input_path))

    mp3s = []
    for f in os.listdir(input_path):
        if f.lower().endswith(".mp3"):
            mp3s.append(os.path.join(input_path, f))

    mp3s = natsorted(mp3s, key=os.path.basename)

    if not mp3s:
        raise click.ClickException("No MP3 files found in {}".format(input_path))

    return mp3s


def find_cover_image(input_path: str) -> str | None:
    """Find the first image file in the input directory."""
    for f in sorted(os.listdir(input_path)):
        if f.lower().endswith((".jpg", ".jpeg", ".png")):
            return os.path.join(input_path, f)
    return None


def determine_bitrate(audio_files: list) -> int:
    """Determine output bitrate from input files.

    Uses the max input bitrate, floored at 64kbps, capped at 256kbps.
    """
    max_bitrate = max((af.bitrate for af in audio_files), default=128)
    return max(64, min(256, max_bitrate))


def convert(
    input_path: str,
    output: str | None = None,
    title: str | None = None,
    author: str | None = None,
    narrator: str | None = None,
    series: str | None = None,
    year: str | None = None,
    genre: str | None = None,
    description: str | None = None,
    cover: str | None = None,
    manifest_path: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """Run the full conversion pipeline."""
    ensure_ffmpeg()
    ensure_ffprobe()

    input_path = os.path.abspath(input_path)

    # Load manifest if available
    manifest = None
    manifest_titles = None
    if manifest_path:
        manifest = load_manifest(manifest_path)
    elif find_manifest(input_path):
        manifest = load_manifest(find_manifest(input_path))

    # Discover and order files
    if manifest:
        ordered_paths = get_file_order(manifest, input_path)
        if ordered_paths:
            mp3_paths = ordered_paths
        else:
            mp3_paths = discover_mp3s(input_path)
        manifest_titles = get_chapter_titles(manifest)
    else:
        mp3_paths = discover_mp3s(input_path)

    # Probe files
    click.echo("Probing {} files...".format(len(mp3_paths)))
    audio_files = probe_files(mp3_paths)

    # Build metadata (manifest -> auto-detect -> CLI overrides)
    if manifest:
        metadata = get_metadata(manifest)
    else:
        metadata = detect_book_metadata(audio_files)

    # CLI flags override everything
    if title is not None:
        metadata.title = title
    if author is not None:
        metadata.author = author
    if narrator is not None:
        metadata.narrator = narrator
    if series is not None:
        metadata.series = series
    if year is not None:
        metadata.year = year
    if genre is not None:
        metadata.genre = genre
    if description is not None:
        metadata.description = description

    # Resolve output path (after metadata is known)
    if output is None:
        if metadata.title:
            output = os.path.join(input_path, "{}.m4b".format(metadata.title))
        else:
            output = os.path.join(input_path, "audiobook.m4b")

    # Resolve cover image
    cover_path = None
    if cover:
        cover_path = os.path.abspath(cover)
    elif metadata.cover:
        candidate = os.path.join(input_path, metadata.cover)
        if os.path.isfile(candidate):
            cover_path = candidate
    if not cover_path:
        found = find_cover_image(input_path)
        if found:
            cover_path = found

    # Build chapters
    chapters = build_chapters(audio_files, manifest_titles)

    # Determine output bitrate
    bitrate = determine_bitrate(audio_files)

    if dry_run:
        _print_dry_run(metadata, chapters, bitrate, cover_path, output)
        return

    # Run the actual conversion
    _run_ffmpeg(
        audio_files=audio_files,
        metadata=metadata,
        chapters=chapters,
        bitrate=bitrate,
        cover_path=cover_path,
        output_path=output,
        verbose=verbose,
    )


def _print_dry_run(
    metadata: BookMetadata,
    chapters: list[Chapter],
    bitrate: int,
    cover_path: str | None,
    output: str,
) -> None:
    """Print the conversion plan without executing."""
    click.echo("\n--- Dry Run ---\n")

    click.echo("Metadata:")
    if metadata.title:
        click.echo("  Title:    {}".format(metadata.title))
    if metadata.author:
        click.echo("  Author:   {}".format(metadata.author))
    if metadata.narrator:
        click.echo("  Narrator: {}".format(metadata.narrator))
    if metadata.series:
        click.echo("  Series:   {}".format(metadata.series))
    if metadata.year:
        click.echo("  Year:     {}".format(metadata.year))
    if metadata.genre:
        click.echo("  Genre:    {}".format(metadata.genre))
    if metadata.description:
        click.echo("  Desc:     {}".format(metadata.description))
    click.echo("  Bitrate:  {} kbps (AAC)".format(bitrate))
    click.echo("  Cover:    {}".format(cover_path or "(none)"))
    click.echo("  Output:   {}".format(output))

    click.echo("\nChapters ({}):\n".format(len(chapters)))
    total_ms = 0
    for i, ch in enumerate(chapters, 1):
        dur = ch.end_ms - ch.start_ms
        total_ms += dur
        click.echo(
            "  {:3d}. {} [{}]  ({})".format(
                i, ch.title, format_duration(dur), ch.source_file
            )
        )

    click.echo("\nTotal duration: {}".format(format_duration(total_ms)))
    click.echo("")


def _pick_aac_encoder() -> str:
    """Use Apple AudioToolbox encoder on macOS if available, else default aac."""
    if platform.system() != "Darwin":
        return "aac"
    try:
        result = subprocess.run(
            [ensure_ffmpeg(), "-encoders"],
            capture_output=True, text=True,
        )
        if "aac_at" in result.stdout:
            return "aac_at"
    except Exception:
        pass
    return "aac"


def _run_ffmpeg(
    audio_files: list,
    metadata: BookMetadata,
    chapters: list[Chapter],
    bitrate: int,
    cover_path: str | None,
    output_path: str,
    verbose: bool,
) -> None:
    """Execute ffmpeg to produce the M4B file."""
    ffmpeg = ensure_ffmpeg()
    tmpdir = tempfile.mkdtemp(prefix="audiobook_")
    total_ms = sum(af.duration_ms for af in audio_files)
    encoder = _pick_aac_encoder()

    try:
        # Write concat file
        concat_path = os.path.join(tmpdir, "filelist.txt")
        with open(concat_path, "w") as f:
            for af in audio_files:
                escaped = af.path.replace("'", "'\\''")
                f.write("file '{}'\n".format(escaped))

        # Write FFMETADATA file
        meta_path = os.path.join(tmpdir, "metadata.txt")
        meta_content = generate_ffmetadata(metadata, chapters)
        with open(meta_path, "w") as f:
            f.write(meta_content)

        # Build ffmpeg command
        cmd = [
            ffmpeg,
            "-f", "concat",
            "-safe", "0",
            "-i", concat_path,
            "-i", meta_path,
        ]

        if cover_path and os.path.isfile(cover_path):
            cmd.extend(["-i", cover_path])
            cmd.extend(["-map", "0:a", "-map", "2:v"])
            cmd.extend(["-c:v", "copy", "-disposition:v", "attached_pic"])
        else:
            cmd.extend(["-map", "0:a"])

        cmd.extend([
            "-c:a", encoder,
            "-b:a", "{}k".format(bitrate),
            "-ar", "44100",
            "-threads", "0",
            "-map_metadata", "1",
            "-map_chapters", "1",
        ])

        # Add progress output unless verbose (which shows raw ffmpeg output)
        if not verbose:
            cmd.extend(["-progress", "pipe:1", "-nostats"])

        cmd.extend(["-y", output_path])

        click.echo(
            "Converting {} files to M4B ({} encoder, {} kbps)...".format(
                len(audio_files), encoder, bitrate
            )
        )

        if verbose:
            subprocess.run(cmd, check=True)
        else:
            _run_with_progress(cmd, total_ms)

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        click.echo("Done! Output: {} ({:.1f} MB)".format(output_path, size_mb))

    finally:
        import shutil as _shutil
        _shutil.rmtree(tmpdir, ignore_errors=True)


def _run_with_progress(cmd: list, total_ms: int) -> None:
    """Run ffmpeg and display a progress bar by parsing -progress output."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    bar_width = 40
    last_pct = -1

    try:
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us="):
                try:
                    time_us = int(line.split("=", 1)[1])
                except (ValueError, IndexError):
                    continue
                time_ms = time_us // 1000
                if total_ms > 0:
                    pct = min(100, int(time_ms * 100 / total_ms))
                else:
                    pct = 0

                if pct != last_pct:
                    last_pct = pct
                    filled = int(bar_width * pct / 100)
                    bar = "#" * filled + "-" * (bar_width - filled)
                    elapsed_str = format_duration(time_ms)
                    total_str = format_duration(total_ms)
                    sys.stderr.write(
                        "\r  [{}] {:3d}%  {}/{}".format(
                            bar, pct, elapsed_str, total_str
                        )
                    )
                    sys.stderr.flush()

        proc.wait()
        # Clear the progress line
        sys.stderr.write("\r" + " " * 80 + "\r")
        sys.stderr.flush()

        if proc.returncode != 0:
            stderr = proc.stderr.read()
            click.echo("ffmpeg error:", err=True)
            click.echo(stderr, err=True)
            raise click.ClickException("ffmpeg conversion failed")
    except Exception:
        proc.kill()
        proc.wait()
        raise

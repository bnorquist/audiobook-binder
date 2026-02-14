"""Click CLI entry point for the audiobook converter."""

from __future__ import annotations

import os

import click

from audiobook_binder.converter import convert, discover_mp3s, find_cover_image
from audiobook_binder.manifest import generate_manifest_yaml
from audiobook_binder.metadata import (
    detect_book_metadata,
    format_duration,
    read_id3_tags,
    resolve_chapter_name,
)
from audiobook_binder.probe import ensure_ffprobe, probe_files


@click.group()
@click.version_option()
def cli():
    """Convert MP3 files into M4B audiobooks with chapters and metadata."""
    pass


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, file_okay=False))
@click.option(
    "-o", "--output",
    default=None,
    help="Output manifest path (default: INPUT_PATH/manifest.yml)",
)
def init(input_path: str, output: str | None):
    """Generate a pre-filled manifest from MP3 files.

    Scans INPUT_PATH for MP3 files, probes each for metadata, and writes
    a manifest.yml that you can edit before converting.
    """
    ensure_ffprobe()
    input_path = os.path.abspath(input_path)

    # Discover and probe MP3s
    mp3_paths = discover_mp3s(input_path)
    click.echo("Found {} MP3 files".format(len(mp3_paths)))

    audio_files = probe_files(mp3_paths)

    # Auto-detect metadata
    metadata = detect_book_metadata(audio_files)

    # Find cover image
    cover = find_cover_image(input_path)
    if cover:
        metadata.cover = os.path.basename(cover)
        click.echo("Found cover image: {}".format(metadata.cover))

    # Build chapter list for manifest
    chapters = []
    for af in audio_files:
        mutagen_tags = read_id3_tags(af.path)
        title = resolve_chapter_name(af, mutagen_tags)
        chapters.append({
            "file": af.filename,
            "title": title,
            "duration": format_duration(af.duration_ms),
        })

    # Generate manifest
    manifest_content = generate_manifest_yaml(metadata, chapters, input_path)

    # Write manifest
    output_path = output or os.path.join(input_path, "manifest.yml")
    with open(output_path, "w") as f:
        f.write(manifest_content)

    click.echo(
        "\nGenerated {} with {} chapters.".format(output_path, len(chapters))
    )
    click.echo(
        "Edit it to customize chapter names and metadata, then run:\n"
        "  audiobook-binder convert {}".format(input_path)
    )


@cli.command(name="convert")
@click.argument("input_path", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", default=None, help="Output .m4b file path (default: INPUT_PATH/audiobook.m4b)")
@click.option("--title", default=None, help="Book title")
@click.option("--author", default=None, help="Author name")
@click.option("--narrator", default=None, help="Narrator name")
@click.option("--series", default=None, help="Series name")
@click.option("--year", default=None, help="Publication year")
@click.option("--genre", default=None, help='Genre (default: "Audiobook")')
@click.option("--description", default=None, help="Book description")
@click.option("--cover", default=None, type=click.Path(exists=True), help="Cover image path")
@click.option("--manifest", default=None, type=click.Path(exists=True), help="Path to YAML manifest")
@click.option("--dry-run", is_flag=True, help="Show plan without converting")
@click.option("--verbose", is_flag=True, help="Show ffmpeg output")
def convert_cmd(
    input_path: str,
    output: str,
    title: str | None,
    author: str | None,
    narrator: str | None,
    series: str | None,
    year: str | None,
    genre: str | None,
    description: str | None,
    cover: str | None,
    manifest: str | None,
    dry_run: bool,
    verbose: bool,
):
    """Convert MP3 files to a single M4B audiobook.

    INPUT_PATH is a directory containing MP3 files.
    """
    convert(
        input_path=input_path,
        output=output,
        title=title,
        author=author,
        narrator=narrator,
        series=series,
        year=year,
        genre=genre,
        description=description,
        cover=cover,
        manifest_path=manifest,
        dry_run=dry_run,
        verbose=verbose,
    )

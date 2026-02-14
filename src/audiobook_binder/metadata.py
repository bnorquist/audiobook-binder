"""Metadata extraction and FFMETADATA1 generation."""

from __future__ import annotations

import os
import re

from mutagen.id3 import ID3
from mutagen.mp3 import MP3

from audiobook_binder.models import AudioFile, BookMetadata, Chapter


def read_id3_tags(filepath: str) -> dict:
    """Read ID3 tags from an MP3 file using mutagen."""
    tags = {}
    try:
        audio = MP3(filepath)
        if audio.tags is None:
            return tags
        id3 = audio.tags

        # Map common ID3 frames to simple keys
        frame_map = {
            "TIT2": "title",
            "TPE1": "artist",
            "TALB": "album",
            "TDRC": "date",
            "TYER": "year",
            "TCON": "genre",
            "TPE2": "album_artist",
            "TCOM": "composer",
        }
        for frame_id, key in frame_map.items():
            frame = id3.get(frame_id)
            if frame:
                tags[key] = str(frame.text[0])
    except Exception:
        pass
    return tags


def clean_chapter_name(filename: str) -> str:
    """Derive a chapter name from a filename.

    Strips numbering prefixes, underscores, and extensions.
    Examples:
        "01_intro.mp3" -> "Intro"
        "03 - Chapter Three.mp3" -> "Chapter Three"
        "chapter_02.mp3" -> "Chapter 02"
    """
    name = os.path.splitext(filename)[0]
    # Strip leading numbers, separators like " - ", "_", "."
    name = re.sub(r"^\d+[\s._-]*(?:-\s*)?", "", name)
    # Replace underscores with spaces
    name = name.replace("_", " ")
    name = name.strip()
    # Title-case if it's all lowercase
    if name == name.lower():
        name = name.title()
    return name if name else filename


def resolve_chapter_name(
    audio_file: AudioFile,
    mutagen_tags: dict | None = None,
    manifest_title: str | None = None,
) -> str:
    """Resolve chapter name in priority: manifest > ID3 title > cleaned filename."""
    if manifest_title:
        return manifest_title

    # Try ID3 title from ffprobe tags
    title = audio_file.tags.get("title", "").strip()
    if title:
        return title

    # Try mutagen tags
    if mutagen_tags and mutagen_tags.get("title", "").strip():
        return mutagen_tags["title"].strip()

    return clean_chapter_name(audio_file.filename)


def build_chapters(
    audio_files: list[AudioFile],
    manifest_titles: dict[str, str] | None = None,
) -> list[Chapter]:
    """Build chapter list with cumulative timestamps from ordered audio files."""
    chapters = []
    current_ms = 0

    for af in audio_files:
        manifest_title = None
        if manifest_titles:
            manifest_title = manifest_titles.get(af.filename)

        mutagen_tags = read_id3_tags(af.path)
        title = resolve_chapter_name(af, mutagen_tags, manifest_title)

        chapter = Chapter(
            title=title,
            start_ms=current_ms,
            end_ms=current_ms + af.duration_ms,
            source_file=af.filename,
        )
        chapters.append(chapter)
        current_ms += af.duration_ms

    return chapters


def detect_book_metadata(audio_files: list[AudioFile]) -> BookMetadata:
    """Auto-detect book metadata from consistent ID3 tags across files."""
    if not audio_files:
        return BookMetadata()

    # Collect tags from all files
    all_tags = [af.tags for af in audio_files]

    def consistent_tag(key: str) -> str:
        """Return the tag value if consistent across all files, else empty."""
        values = {t.get(key, "").strip() for t in all_tags}
        values.discard("")
        if len(values) == 1:
            return values.pop()
        return ""

    return BookMetadata(
        title=consistent_tag("album"),
        author=consistent_tag("artist") or consistent_tag("album_artist"),
        narrator=consistent_tag("composer"),
        year=consistent_tag("date") or consistent_tag("year"),
        genre=consistent_tag("genre") or "Audiobook",
    )


def generate_ffmetadata(
    metadata: BookMetadata,
    chapters: list[Chapter],
) -> str:
    """Generate FFMETADATA1 content for ffmpeg."""
    lines = [";FFMETADATA1"]

    if metadata.title:
        lines.append("title={}".format(_escape_meta(metadata.title)))
    if metadata.author:
        lines.append("artist={}".format(_escape_meta(metadata.author)))
    if metadata.title:
        lines.append("album={}".format(_escape_meta(metadata.title)))
    if metadata.genre:
        lines.append("genre={}".format(_escape_meta(metadata.genre)))
    if metadata.narrator:
        lines.append("composer={}".format(_escape_meta(metadata.narrator)))
    if metadata.year:
        lines.append("date={}".format(_escape_meta(metadata.year)))
    if metadata.description:
        lines.append("description={}".format(_escape_meta(metadata.description)))

    for ch in chapters:
        lines.append("")
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append("START={}".format(ch.start_ms))
        lines.append("END={}".format(ch.end_ms))
        lines.append("title={}".format(_escape_meta(ch.title)))

    return "\n".join(lines) + "\n"


def _escape_meta(value: str) -> str:
    """Escape special characters for FFMETADATA format."""
    # In FFMETADATA, =, ;, #, and \\ need escaping
    value = value.replace("\\", "\\\\")
    value = value.replace("=", "\\=")
    value = value.replace(";", "\\;")
    value = value.replace("#", "\\#")
    value = value.replace("\n", "\\\n")
    return value


def format_duration(ms: int) -> str:
    """Format milliseconds as M:SS or H:MM:SS."""
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return "{}:{:02d}:{:02d}".format(hours, minutes, seconds)
    return "{}:{:02d}".format(minutes, seconds)

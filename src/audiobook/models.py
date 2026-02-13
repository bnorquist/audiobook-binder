from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AudioFile:
    """Represents a probed MP3 file with its metadata."""

    path: str
    filename: str
    duration_ms: int
    bitrate: int  # in kbps
    sample_rate: int
    tags: dict = field(default_factory=dict)  # ID3 tags: title, artist, album, etc.


@dataclass
class Chapter:
    """A chapter in the output audiobook."""

    title: str
    start_ms: int
    end_ms: int
    source_file: str


@dataclass
class BookMetadata:
    """Metadata for the output audiobook."""

    title: str = ""
    author: str = ""
    narrator: str = ""
    series: str = ""
    year: str = ""
    genre: str = "Audiobook"
    description: str = ""
    cover: str = ""

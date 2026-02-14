"""Tests for metadata extraction and FFMETADATA generation."""

from audiobook_binder.metadata import (
    build_chapters,
    clean_chapter_name,
    format_duration,
    generate_ffmetadata,
    resolve_chapter_name,
)
from audiobook_binder.models import AudioFile, BookMetadata


def test_clean_chapter_name_strips_numbering():
    assert clean_chapter_name("01_intro.mp3") == "Intro"
    assert clean_chapter_name("03 - Chapter Three.mp3") == "Chapter Three"
    assert clean_chapter_name("chapter_02.mp3") == "Chapter 02"


def test_clean_chapter_name_handles_edge_cases():
    assert clean_chapter_name("track.mp3") == "Track"
    assert clean_chapter_name("01.mp3") != ""


def test_resolve_chapter_name_priority():
    af = AudioFile(
        path="/fake/01.mp3",
        filename="01_intro.mp3",
        duration_ms=1000,
        bitrate=128,
        sample_rate=44100,
        tags={"title": "ID3 Title"},
    )

    # Manifest title takes priority
    assert resolve_chapter_name(af, manifest_title="Manifest Title") == "Manifest Title"

    # ID3 title is second priority
    assert resolve_chapter_name(af) == "ID3 Title"

    # Cleaned filename is fallback
    af_no_tags = AudioFile(
        path="/fake/01.mp3",
        filename="01_intro.mp3",
        duration_ms=1000,
        bitrate=128,
        sample_rate=44100,
        tags={},
    )
    assert resolve_chapter_name(af_no_tags) == "Intro"


def test_build_chapters_cumulative_timestamps():
    files = [
        AudioFile("/f/a.mp3", "a.mp3", 5000, 128, 44100, {"title": "Ch 1"}),
        AudioFile("/f/b.mp3", "b.mp3", 3000, 128, 44100, {"title": "Ch 2"}),
        AudioFile("/f/c.mp3", "c.mp3", 7000, 128, 44100, {"title": "Ch 3"}),
    ]
    chapters = build_chapters(files)

    assert len(chapters) == 3
    assert chapters[0].start_ms == 0
    assert chapters[0].end_ms == 5000
    assert chapters[1].start_ms == 5000
    assert chapters[1].end_ms == 8000
    assert chapters[2].start_ms == 8000
    assert chapters[2].end_ms == 15000


def test_build_chapters_with_manifest_titles():
    files = [
        AudioFile("/f/a.mp3", "a.mp3", 5000, 128, 44100, {"title": "ID3"}),
    ]
    titles = {"a.mp3": "Override Title"}
    chapters = build_chapters(files, manifest_titles=titles)
    assert chapters[0].title == "Override Title"


def test_generate_ffmetadata():
    meta = BookMetadata(title="My Book", author="Author", genre="Audiobook")
    chapters = [
        _chapter("Ch 1", 0, 5000),
        _chapter("Ch 2", 5000, 10000),
    ]
    content = generate_ffmetadata(meta, chapters)

    assert content.startswith(";FFMETADATA1\n")
    assert "title=My Book" in content
    assert "artist=Author" in content
    assert "[CHAPTER]" in content
    assert "TIMEBASE=1/1000" in content
    assert "START=0" in content
    assert "END=5000" in content
    assert "START=5000" in content
    assert "END=10000" in content


def test_generate_ffmetadata_escaping():
    meta = BookMetadata(title="Book; With = Special # Chars")
    content = generate_ffmetadata(meta, [])
    assert "Book\\; With \\= Special \\# Chars" in content


def test_format_duration():
    assert format_duration(0) == "0:00"
    assert format_duration(5000) == "0:05"
    assert format_duration(65000) == "1:05"
    assert format_duration(3661000) == "1:01:01"


def _chapter(title, start, end):
    from audiobook_binder.models import Chapter
    return Chapter(title=title, start_ms=start, end_ms=end, source_file="test.mp3")

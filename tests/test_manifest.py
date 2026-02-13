"""Tests for manifest parsing."""

import os

from audiobook.manifest import (
    generate_manifest_yaml,
    get_chapter_titles,
    get_file_order,
    get_metadata,
    load_manifest,
)
from audiobook.models import BookMetadata


def test_load_manifest(tmp_dir):
    path = os.path.join(tmp_dir, "manifest.yml")
    with open(path, "w") as f:
        f.write('title: "Test Book"\nauthor: "Test Author"\nchapters:\n  - file: "01.mp3"\n    title: "Chapter 1"\n')

    manifest = load_manifest(path)
    assert manifest["title"] == "Test Book"
    assert manifest["author"] == "Test Author"
    assert len(manifest["chapters"]) == 1


def test_get_file_order(tmp_dir):
    # Create dummy MP3 files
    for name in ["a.mp3", "b.mp3"]:
        open(os.path.join(tmp_dir, name), "w").close()

    manifest = {
        "chapters": [
            {"file": "b.mp3", "title": "Second"},
            {"file": "a.mp3", "title": "First"},
        ]
    }
    order = get_file_order(manifest, tmp_dir)
    assert len(order) == 2
    assert order[0].endswith("b.mp3")
    assert order[1].endswith("a.mp3")


def test_get_file_order_returns_none_without_chapters():
    assert get_file_order({}, "/tmp") is None


def test_get_chapter_titles():
    manifest = {
        "chapters": [
            {"file": "01.mp3", "title": "Intro"},
            {"file": "02.mp3", "title": "Chapter 1"},
        ]
    }
    titles = get_chapter_titles(manifest)
    assert titles == {"01.mp3": "Intro", "02.mp3": "Chapter 1"}


def test_get_metadata():
    manifest = {
        "title": "My Book",
        "author": "Author",
        "narrator": "Narrator",
        "year": 2024,
        "genre": "Fiction",
    }
    meta = get_metadata(manifest)
    assert meta.title == "My Book"
    assert meta.author == "Author"
    assert meta.narrator == "Narrator"
    assert meta.year == "2024"
    assert meta.genre == "Fiction"


def test_get_metadata_defaults():
    meta = get_metadata({})
    assert meta.title == ""
    assert meta.genre == "Audiobook"


def test_generate_manifest_yaml():
    meta = BookMetadata(title="Test", author="Auth", cover="cover.jpg")
    chapters = [
        {"file": "01.mp3", "title": "Intro", "duration": "1:23"},
    ]
    content = generate_manifest_yaml(meta, chapters, "./input")
    assert 'title: "Test"' in content
    assert 'author: "Auth"' in content
    assert 'file: "01.mp3"' in content
    assert 'title: "Intro"' in content
    assert 'duration: "1:23"' in content

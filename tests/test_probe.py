"""Tests for the ffprobe wrapper."""

from audiobook_binder.probe import probe_file, probe_files


def test_probe_file_returns_audio_file(make_mp3, tmp_dir):
    path = make_mp3("test.mp3", duration_s=2.0, title="Test Title")
    result = probe_file(path)

    assert result.filename == "test.mp3"
    assert result.duration_ms > 0
    assert result.sample_rate == 44100
    assert result.tags.get("title") == "Test Title"


def test_probe_file_duration_roughly_correct(make_mp3):
    path = make_mp3("short.mp3", duration_s=3.0)
    result = probe_file(path)

    # Allow some tolerance for encoding overhead
    assert 2500 < result.duration_ms < 3500


def test_probe_files_multiple(sample_mp3s):
    import os
    mp3s = sorted(
        os.path.join(sample_mp3s, f)
        for f in os.listdir(sample_mp3s)
        if f.endswith(".mp3")
    )
    results = probe_files(mp3s)
    assert len(results) == 3
    assert all(r.duration_ms > 0 for r in results)

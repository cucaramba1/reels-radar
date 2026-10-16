from reels_radar.local import clean_lines, score


def test_clean_lines_dedups_and_drops_noise():
    blocks = ["Hello world\n12:30\nab", "hello   WORLD\nПривет мир"]
    assert clean_lines(blocks) == ["Hello world", "Привет мир"]


def test_score_monotonic_and_capped():
    kw = ["claude"]
    low = score("", "", "", kw)
    mid = score("слово " * 100, "", "", kw)
    assert low == 0 and mid > low
    assert score("слово " * 10000, "текст " * 10000, "claude " * 50, kw) <= 100


def test_keywords_add_points():
    assert score("", "", "claude mcp", ["claude", "mcp"]) > score("", "", "ничего", ["claude", "mcp"])


def test_whisper_failure_raises(tmp_path, monkeypatch):
    import subprocess
    from reels_radar import local
    monkeypatch.setattr(local.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "boom"))
    import pytest
    with pytest.raises(RuntimeError):
        local.transcribe("w", "m", tmp_path / "v.mp4", tmp_path / "stt")


def test_no_speech_is_empty_not_error(tmp_path, monkeypatch):
    import subprocess
    from reels_radar import local
    def fake(*a, **k):
        (tmp_path / "stt").mkdir(exist_ok=True)
        (tmp_path / "stt" / "v.txt").write_text("")
        return subprocess.CompletedProcess(a, 0, "", "")
    monkeypatch.setattr(local.subprocess, "run", fake)
    assert local.transcribe("w", "m", tmp_path / "v.mp4", tmp_path / "stt") == ""

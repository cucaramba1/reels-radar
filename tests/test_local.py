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
    monkeypatch.setattr(local, "has_audio", lambda v: True)
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
    monkeypatch.setattr(local, "has_audio", lambda v: True)
    monkeypatch.setattr(local.subprocess, "run", fake)
    assert local.transcribe("w", "m", tmp_path / "v.mp4", tmp_path / "stt") == ""


def test_silent_video_is_empty_not_error(tmp_path, monkeypatch):
    from reels_radar import local
    monkeypatch.setattr(local, "has_audio", lambda v: False)
    def boom(*a, **k): raise AssertionError("whisper must not run")
    monkeypatch.setattr(local.subprocess, "run", boom)
    assert local.transcribe("w", "m", tmp_path / "v.mp4", tmp_path / "stt") == ""


def test_image_post_uses_images_and_skips_whisper(tmp_path, monkeypatch):
    from reels_radar import local
    for n in ("1.jpg", "2.jpg"):
        (tmp_path / n).write_bytes(b"x")
    seen = {}
    monkeypatch.setattr(local, "run_ocr", lambda b, paths: seen.setdefault("n", len(paths)) and ["текст слайда"] * len(paths))
    def boom(*a, **k): raise AssertionError("whisper must not run for images")
    monkeypatch.setattr(local, "transcribe", boom)
    class S:
        max_frames = 6; reels_tools = tmp_path; whisper_bin = "w"; whisper_model = "m"; keywords = []
    lr = local.analyze_local(S(), tmp_path, tmp_path / "work", "подпись")
    assert lr.transcript == "" and "текст слайда" in lr.ocr_text and len(lr.frames) == 2

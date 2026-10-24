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
        (tmp_path / "stt" / "v.json").write_text('{"text": "", "segments": []}')
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



def _fake_whisper(tmp_path, monkeypatch, result):
    import json, subprocess
    from reels_radar import local
    def fake(*a, **k):
        (tmp_path / "stt").mkdir(exist_ok=True)
        (tmp_path / "stt" / "v.json").write_text(json.dumps(result, ensure_ascii=False))
        return subprocess.CompletedProcess(a, 0, "", "")
    monkeypatch.setattr(local, "has_audio", lambda v: True)
    monkeypatch.setattr(local.subprocess, "run", fake)
    return local.transcribe("w", "m", tmp_path / "v.mp4", tmp_path / "stt")


def test_music_hallucination_is_dropped(tmp_path, monkeypatch):
    segs = [{"no_speech_prob": 0.8, "avg_logprob": -0.9}, {"no_speech_prob": 0.7, "avg_logprob": -0.7},
            {"no_speech_prob": 0.1, "avg_logprob": -0.2}]
    assert _fake_whisper(tmp_path, monkeypatch, {"text": "Продолжение следует... Субтитры сделал DimaTorzok", "segments": segs}) == ""


def test_real_speech_is_kept(tmp_path, monkeypatch):
    segs = [{"no_speech_prob": 0.02, "avg_logprob": -0.2}, {"no_speech_prob": 0.6, "avg_logprob": -0.3}]
    text = "Сегодня покажу, как настроить Claude Code за пять минут"
    assert _fake_whisper(tmp_path, monkeypatch, {"text": text, "segments": segs}) == text



def test_stock_whisper_phrases_are_dropped(tmp_path, monkeypatch):
    ok = [{"no_speech_prob": 0.0, "avg_logprob": -0.7}]
    for t in ("Thank you.", "Продолжение следует... Субтитры сделал DimaTorzok", "Спасибо за просмотр!"):
        assert _fake_whisper(tmp_path, monkeypatch, {"text": t, "segments": ok}) == ""
    t = "Спасибо за просмотр, а теперь про настройку бота в Telegram"
    assert _fake_whisper(tmp_path, monkeypatch, {"text": t, "segments": ok}) == t


def test_shot_times_one_frame_per_shot_merges_short_and_caps():
    from reels_radar.local import shot_times
    t = shot_times([2, 4, 4.3, 6], 10.0)  # края 0.8 и 9.2; план 4-4.3 короче 0.8 с вливается в предыдущий
    assert len(t) == 4 and all(0.8 < x < 9.2 for x in t)
    assert len(shot_times([i * 0.9 for i in range(1, 60)], 60.0, n_max=10)) == 10


def test_scene_cuts_on_real_ffmpeg(tmp_path):
    import shutil, subprocess
    import pytest
    from reels_radar.local import scene_cuts, shot_times
    if not shutil.which("ffmpeg"):
        pytest.skip("нет ffmpeg")
    colors = ["red", "green", "blue", "yellow", "white", "black", "purple", "orange"]
    src = sum((["-f", "lavfi", "-i", f"color={c}:s=320x240:d=2:r=10"] for c in colors), [])
    flt = "".join(f"[{i}:v]" for i in range(len(colors))) + f"concat=n={len(colors)}:v=1:a=0[v]"
    v = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *src, "-filter_complex", flt, "-map", "[v]", str(v)], check=True)
    cuts = scene_cuts(v)
    # 7 склеек; пару цветов с близкой яркостью детектор при 0.2 может не различить, это не страшно
    assert len(cuts) >= 5 and all(abs(c - round(c / 2) * 2) < 0.3 for c in cuts)
    assert len(shot_times(cuts, 16.0)) == len(cuts)  # крайние полупланы влились в соседей

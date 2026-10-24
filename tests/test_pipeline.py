import asyncio
from pathlib import Path
from reels_radar.config import Theme
from reels_radar.local import LocalResult
from reels_radar.pipeline import run_batch
from reels_radar.vision import Verdict

THEMES = {"ИИ": Theme("ИИ", "f", "m"), "Разное": Theme("Разное", "f", "m")}


class S:
    select_threshold = 30
    data_dir = None


def mk_local(score):
    return lambda video, workdir, caption: LocalResult("речь", "ocr", score, [])


async def ok_classify(row, lr):
    return Verdict("ИИ", ["note"], "знание", "с", "", "Т", "тело")


def ok_fetch(row, workdir):
    p = Path(workdir) / "v.mp4"; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"x")
    return "OK", p


def run(db, tmp_path, **kw):
    s = S(); s.data_dir = tmp_path
    return asyncio.run(run_batch(s, db, THEMES, **kw))


def test_high_score_becomes_draft(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    run(db, tmp_path, fetch=ok_fetch, local=mk_local(80), classify=ok_classify)
    assert db.get("A")["status"] == "draft" and not (tmp_path / "work" / "A").exists()


def test_low_score_archived_without_claude(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    async def boom(row, lr): raise AssertionError("claude must not be called")
    run(db, tmp_path, fetch=ok_fetch, local=mk_local(5), classify=boom)
    assert db.get("A")["status"] == "archived"


def test_no_video_stays_in_queue(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    run(db, tmp_path, fetch=lambda r, w: ("NO_VIDEO", None), local=mk_local(80), classify=ok_classify)
    r = db.get("A")
    assert r["status"] == "no_video" and r["attempts"] == 1


def test_rate_pauses_queue(db, tmp_path):
    db.add_item("A", "u", "c", 1); db.add_item("B", "u", "c", 2)
    run(db, tmp_path, fetch=lambda r, w: ("RATE", None), local=mk_local(80), classify=ok_classify)
    assert db.kv_get("paused") == "1" and db.get("A")["status"] == "new" and db.get("B")["status"] == "new"


def test_claude_limit_pauses_keeps_local(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    async def limit(row, lr): raise RuntimeError("usage limit reached")
    run(db, tmp_path, fetch=ok_fetch, local=mk_local(80), classify=limit)
    assert db.kv_get("paused") == "1" and db.get("A")["status"] == "new"


def test_limit_returns_item_to_queue_and_next_run_continues(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    async def limit(row, lr): raise RuntimeError("usage limit reached")
    run(db, tmp_path, fetch=ok_fetch, local=mk_local(80), classify=limit)
    assert db.get("A")["status"] == "new"
    run(db, tmp_path, fetch=ok_fetch, local=mk_local(80), classify=ok_classify)
    assert db.get("A")["status"] == "draft" and db.kv_get("paused") == "0"


def test_one_crash_does_not_kill_batch(db, tmp_path):
    db.add_item("A", "u", "c", 2); db.add_item("B", "u", "c", 1)
    def flaky(row, w):
        if row["code"] == "A":
            raise TimeoutError("yt-dlp hung")
        return ok_fetch(row, w)
    run(db, tmp_path, fetch=flaky, local=mk_local(80), classify=ok_classify)
    assert db.get("A")["status"] == "failed" and db.get("A")["attempts"] == 1
    assert db.get("B")["status"] == "draft"


def test_failed_is_retried_up_to_three(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    def boom(row, w): raise TimeoutError("x")
    for _ in range(5):
        run(db, tmp_path, fetch=boom, local=mk_local(80), classify=ok_classify)
    assert db.get("A")["status"] == "failed" and db.get("A")["attempts"] == 3


def test_login_pauses_without_burning_attempts(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    run(db, tmp_path, fetch=lambda r, w: ("LOGIN", None), local=mk_local(80), classify=ok_classify)
    r = db.get("A")
    assert db.kv_get("paused") == "1" and r["status"] == "new" and r["attempts"] == 0


def test_whisper_failure_is_failed_not_archived(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    def bad_local(video, workdir, caption): raise RuntimeError("whisper failed")
    async def boom(row, lr): raise AssertionError("no")
    run(db, tmp_path, fetch=ok_fetch, local=bad_local, classify=boom)
    assert db.get("A")["status"] == "failed"


def test_light_night_defers_videos_without_penalty_and_runs_carousels(db, tmp_path):
    db.add_item("R", "https://www.instagram.com/reel/R/", "c", 1)
    db.add_item("V", "https://www.instagram.com/p/V/", "c", 2)  # пост /p/, а внутри видео
    db.add_item("C", "https://www.instagram.com/p/C/", "c", 3)
    fetched = []

    def fetch(row, workdir):
        fetched.append(row["code"])
        if row["code"] == "C":
            d = Path(workdir); d.mkdir(parents=True, exist_ok=True); (d / "1.jpg").write_bytes(b"x")
            return "OK", d
        return ok_fetch(row, workdir)

    stats = run(db, tmp_path, fetch=fetch, local=mk_local(80), classify=ok_classify, light=True)
    assert "R" not in fetched and stats["deferred"] == 2
    for code in ("R", "V"):
        assert (db.get(code)["status"], db.get(code)["attempts"]) == ("new", 0)
    assert db.get("C")["status"] == "draft"

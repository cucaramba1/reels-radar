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
    assert db.kv_get("paused") == "1" and db.get("A")["status"] == "local"

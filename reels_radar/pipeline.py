from __future__ import annotations

import shutil
from pathlib import Path

from .claude import is_limit
from .review import save_verdict


async def run_batch(s, db, themes, *, fetch, local, classify, limit=None) -> dict[str, int]:
    rows = [*db.by_status("new", limit or 1000), *db.by_status("no_video", limit or 1000)]
    rows = [r for r in rows if r["attempts"] < 3][: limit or None]
    stats = {"draft": 0, "archived": 0, "no_video": 0, "paused": 0}
    for r in rows:
        code = r["code"]
        work = Path(s.data_dir) / "work" / code
        try:
            status, video = fetch(r, work)
            if status == "RATE":
                db.kv_set("paused", "1"); stats["paused"] = 1
                break
            if status != "OK":
                db.update(code, status="no_video", attempts=r["attempts"] + 1, fail_reason=status)
                stats["no_video"] += 1
                continue
            lr = local(video, work, r["caption"])
            db.update(code, status="local", transcript=lr.transcript, ocr_text=lr.ocr_text, score=lr.score)
            if lr.score < s.select_threshold:
                db.update(code, status="archived"); stats["archived"] += 1
                continue
            try:
                v = await classify(db.get(code), lr)
            except Exception as e:
                if is_limit(e):
                    db.kv_set("paused", "1"); stats["paused"] = 1
                    break
                db.update(code, status="failed", attempts=r["attempts"] + 1, fail_reason=str(e)[:200])
                continue
            save_verdict(db, code, v)
            stats["archived" if v.skip else "draft"] += 1
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return stats

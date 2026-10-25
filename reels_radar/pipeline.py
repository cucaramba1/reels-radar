from __future__ import annotations

import shutil
from pathlib import Path

from .claude import is_limit
from .review import save_verdict
from .slot import should_yield

MAX_ATTEMPTS = 3
PAUSE_ALERT = {
    "LOGIN": "🔑 Instagram просит логин: сессия в куках умерла, ночь на паузе. Обнови tools/reels/ig_cookies.txt "
             "(экспорт кук из браузера, где IG залогинен), рилсы подождут без штрафа.",
    "RATE": "⏳ Instagram ограничил запросы (429), ночь на паузе. Ничего делать не надо, следующая ночь продолжит.",
}


def _is_reel(url: str) -> bool:
    return "/reel/" in url or "/reels/" in url or "/tv/" in url


async def run_batch(s, db, themes, *, fetch, local, classify, limit=None, light=False,
                    yield_check=should_yield) -> dict[str, int]:
    """light: мало диска. Видео ждут следующей ночи без штрафа, карусели и фото разбираются как обычно."""
    db.kv_set("paused", "0")  # пауза живёт один прогон, следующий продолжает сам
    n = limit or 1000
    rows = [*db.by_status("new", n), *db.by_status("no_video", n), *db.by_status("failed", n)]
    rows = [r for r in rows if r["attempts"] < MAX_ATTEMPTS][: limit or None]
    stats = {"draft": 0, "archived": 0, "no_video": 0, "failed": 0, "paused": 0, "deferred": 0}
    for r in rows:
        if yield_check():
            stats["yielded"] = 1  # остальные остаются new, следующий прогон продолжит
            break
        code = r["code"]
        if light and _is_reel(r["url"]):
            stats["deferred"] += 1  # статус и попытки не трогаем
            continue
        work = Path(s.data_dir) / "work" / code
        try:
            status, video = fetch(r, work)
            if status in ("RATE", "LOGIN"):
                db.kv_set("paused", "1"); stats["paused"] = 1
                db.kv_set("alert", PAUSE_ALERT[status])  # бот пришлёт в ближайшие 5 минут
                break
            if status != "OK":
                db.update(code, status="no_video", attempts=r["attempts"] + 1, fail_reason=status)
                stats["no_video"] += 1
                continue
            if light and not Path(video).is_dir():  # пост /p/ оказался видео
                stats["deferred"] += 1
                continue
            lr = local(video, work, r["caption"])
            db.update(code, transcript=lr.transcript, ocr_text=lr.ocr_text, score=lr.score)
            if lr.score < s.select_threshold:
                db.update(code, status="archived", fail_reason=None); stats["archived"] += 1
                continue
            try:
                v = await classify(db.get(code), lr)
            except Exception as e:
                if is_limit(e):
                    db.kv_set("paused", "1"); stats["paused"] = 1
                    break  # статус не меняем: рилс остаётся в очереди
                raise
            save_verdict(db, code, v)
            stats["archived" if v.skip else "draft"] += 1
        except Exception as e:
            db.update(code, status="failed", attempts=r["attempts"] + 1, fail_reason=str(e)[:200])
            stats["failed"] += 1
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return stats

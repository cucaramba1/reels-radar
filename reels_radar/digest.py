from __future__ import annotations

from datetime import date, datetime
from pathlib import PurePosixPath


def _stale(version: str, days: int = 45) -> bool:
    try:
        y, m, d = (int(x) for x in version.strip().split(".")[:3])
        return (date.today() - date(y, m, d)).days > days
    except ValueError:
        return False


def _top(db, where, args, n):
    return db.c.execute(f"SELECT * FROM items WHERE status IN ('draft','approved','written') AND {where} "
                        f"AND updated >= ? ORDER BY score DESC LIMIT ?", (*args, n)).fetchall()


def _by_folder(db, since_iso: str) -> list[str]:
    """Куда ушли сохранёнки за неделю, без LLM: папка, сколько, три названия (идея из kurbaitaev/saved-to-notes)."""
    groups: dict[str, list[str]] = {}
    for r in db.c.execute("SELECT title, note_path FROM items WHERE status='written' AND note_path IS NOT NULL "
                          "AND updated >= ? ORDER BY updated DESC", (since_iso,)):
        groups.setdefault(PurePosixPath(r["note_path"]).parent.name or "корень", []).append(r["title"] or "?")
    out = []
    for folder, titles in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        more = f" +{len(titles) - 3}" if len(titles) > 3 else ""
        out.append(f"- {folder}: {len(titles)} ({', '.join(titles[:3])}{more})")
    return out


def _repeat(db, since_iso: str, mark: bool) -> str | None:
    """Одна старая заметка, к которой ещё не возвращались: чтобы сохранённое не умирало."""
    r = db.c.execute("SELECT code, title, note_path FROM items WHERE status='written' AND note_path IS NOT NULL "
                     "AND updated < ? AND code NOT IN (SELECT substr(k, 10) FROM kv WHERE k LIKE 'repeated:%') "
                     "ORDER BY random() LIMIT 1", (since_iso,)).fetchone()
    if r is None:
        return None
    if mark:
        db.kv_set(f"repeated:{r['code']}", datetime.now().date().isoformat())
    return f"«{r['title']}» ({r['note_path']})\nПрименил? Если нет, что мешает: сделать на этой неделе или удалить?"


def build_digest(db, since_iso: str, mark_repeat: bool = False, ytdlp_version: str | None = None) -> str:
    out = ["Недельный дайджест"]
    if folders := _by_folder(db, since_iso):
        out += ["", "Куда ушли сохранёнки:"] + folders
    content = _top(db, "purposes LIKE ?", ("%content%", since_iso), 5)
    if content:
        out += ["", "Для контента:"] + [f"- {r['summary']}\n  {r['template']}\n  {r['url']}" for r in content]
    claude = _top(db, "purposes LIKE ?", ("%claude%", since_iso), 5)
    if claude:
        out += ["", "Фичи и приёмы Claude:"] + [f"- {r['summary']}\n  {r['url']}" for r in claude]
    words = _top(db, "theme = ?", ("Слова и фразы", since_iso), 5)
    if words:
        out += ["", "Слова и фразы:"] + [f"- {r['summary']}" for r in words]
    need = db.c.execute("SELECT url FROM items WHERE status='no_video' AND attempts>=1 LIMIT 20").fetchall()
    if need:
        out += ["", "Нужен файл (видео не скачалось):"] + [f"- {r['url']}" for r in need]
    if rep := _repeat(db, since_iso, mark_repeat):
        out += ["", "🔁 Из старого:", rep]
    if ytdlp_version and _stale(ytdlp_version):
        out += ["", f"⚠ yt-dlp {ytdlp_version} старше 45 дней, Instagram ломает старые версии: brew upgrade yt-dlp"]
    out += ["", "Счётчики: " + ", ".join(f"{k} {v}" for k, v in sorted(db.counts().items()))]
    return "\n".join(out).replace("—", "-")

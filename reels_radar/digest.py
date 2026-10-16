from __future__ import annotations


def _top(db, where, args, n):
    return db.c.execute(f"SELECT * FROM items WHERE status IN ('draft','approved','written') AND {where} "
                        f"AND updated >= ? ORDER BY score DESC LIMIT ?", (*args, n)).fetchall()


def build_digest(db, since_iso: str) -> str:
    out = ["Недельный дайджест"]
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
    out += ["", "Счётчики: " + ", ".join(f"{k} {v}" for k, v in sorted(db.counts().items()))]
    return "\n".join(out).replace("—", "-")

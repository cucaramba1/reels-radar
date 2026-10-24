from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  code TEXT PRIMARY KEY, url TEXT NOT NULL, caption TEXT NOT NULL DEFAULT '',
  ts INTEGER NOT NULL DEFAULT 0, folder TEXT, owner TEXT,
  status TEXT NOT NULL DEFAULT 'new', attempts INTEGER NOT NULL DEFAULT 0, fail_reason TEXT,
  ocr_text TEXT, transcript TEXT, score REAL,
  theme TEXT, purposes TEXT, kind TEXT, summary TEXT, template TEXT, title TEXT, body TEXT,
  note_path TEXT, note_created INTEGER, moc_line TEXT,
  updated TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS items_status ON items(status);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""

FIELDS = {"url", "caption", "ts", "folder", "owner", "status", "attempts", "fail_reason", "ocr_text", "transcript",
          "score", "theme", "purposes", "kind", "summary", "template", "title", "body", "note_path",
          "note_created", "moc_line", "decision", "note_vault", "moc_rel", "canvas_rel"}


class DB:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(str(path), timeout=30)
        self.c.row_factory = sqlite3.Row
        self.c.execute("PRAGMA journal_mode=WAL")  # бот и ночной прогон пишут в одну базу
        self.c.executescript(SCHEMA)
        for col in ("owner", "decision", "note_vault", "moc_rel", "canvas_rel"):
            try:
                self.c.execute(f"ALTER TABLE items ADD COLUMN {col} TEXT")
                self.c.commit()
            except sqlite3.OperationalError:
                pass  # колонка уже есть

    def add_item(self, code, url, caption, ts, folder=None, owner=None) -> bool:
        cur = self.c.execute(
            "INSERT OR IGNORE INTO items(code,url,caption,ts,folder,owner,updated) VALUES(?,?,?,?,?,?,?)",
            (code, url, caption, ts, folder, owner, datetime.now().isoformat()))
        self.c.commit()
        return cur.rowcount == 1

    def get(self, code):
        return self.c.execute("SELECT * FROM items WHERE code=?", (code,)).fetchone()

    def by_status(self, status, limit=100):
        return self.c.execute("SELECT * FROM items WHERE status=? ORDER BY ts DESC LIMIT ?",
                              (status, limit)).fetchall()

    def update(self, code, **fields):
        bad = set(fields) - FIELDS
        if bad:
            raise KeyError(f"unknown fields: {bad}")
        fields["updated"] = datetime.now().isoformat()
        sets = ",".join(f"{k}=?" for k in fields)
        self.c.execute(f"UPDATE items SET {sets} WHERE code=?", (*fields.values(), code))
        self.c.commit()

    def counts(self) -> dict[str, int]:
        return {r[0]: r[1] for r in self.c.execute("SELECT status, COUNT(*) FROM items GROUP BY status")}

    def search(self, query: str, limit: int = 10) -> list:
        """Поиск по названию, сути, речи и тексту на экране (FTS5, слова по префиксу: «монтаж» найдёт «монтажёр»).
        Индекс временный, в памяти: строк мало, а без триггеров нечему рассинхронизироваться."""
        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 1]
        if not words:
            return []
        self.c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.f USING fts5(code UNINDEXED, title, summary, transcript, ocr)")
        self.c.execute("DELETE FROM temp.f")
        self.c.execute("INSERT INTO temp.f SELECT code, title, summary, transcript, ocr_text FROM items "
                       "WHERE status NOT IN ('new','failed','no_video')")
        q = " ".join(f'"{w}"*' for w in words)
        return self.c.execute("SELECT i.* FROM temp.f JOIN items i ON i.code=f.code WHERE f MATCH ? "
                              "ORDER BY bm25(f) LIMIT ?", (q, limit)).fetchall()

    def kv_get(self, key, default=None):
        r = self.c.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
        return r[0] if r else default

    def kv_set(self, key, value):
        self.c.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                       (key, str(value)))
        self.c.commit()

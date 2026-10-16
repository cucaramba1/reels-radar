from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  code TEXT PRIMARY KEY, url TEXT NOT NULL, caption TEXT NOT NULL DEFAULT '',
  ts INTEGER NOT NULL DEFAULT 0, folder TEXT,
  status TEXT NOT NULL DEFAULT 'new', attempts INTEGER NOT NULL DEFAULT 0, fail_reason TEXT,
  ocr_text TEXT, transcript TEXT, score REAL,
  theme TEXT, purposes TEXT, kind TEXT, summary TEXT, template TEXT, title TEXT, body TEXT,
  note_path TEXT, note_created INTEGER, moc_line TEXT,
  updated TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS items_status ON items(status);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""

FIELDS = {"url", "caption", "ts", "folder", "status", "attempts", "fail_reason", "ocr_text", "transcript",
          "score", "theme", "purposes", "kind", "summary", "template", "title", "body", "note_path",
          "note_created", "moc_line"}


class DB:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(str(path))
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)

    def add_item(self, code, url, caption, ts, folder=None) -> bool:
        cur = self.c.execute(
            "INSERT OR IGNORE INTO items(code,url,caption,ts,folder,updated) VALUES(?,?,?,?,?,?)",
            (code, url, caption, ts, folder, datetime.now().isoformat()))
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

    def kv_get(self, key, default=None):
        r = self.c.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
        return r[0] if r else default

    def kv_set(self, key, value):
        self.c.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                       (key, str(value)))
        self.c.commit()

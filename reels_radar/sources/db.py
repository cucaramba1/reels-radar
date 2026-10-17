from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  username TEXT PRIMARY KEY, platform TEXT NOT NULL DEFAULT 'instagram',
  status TEXT NOT NULL DEFAULT 'candidate', intent TEXT NOT NULL DEFAULT 'none',
  themes TEXT, priority REAL NOT NULL DEFAULT 0, value_score REAL, posts_per_week REAL,
  last_post_at TEXT, last_reel_at TEXT, last_collab_at TEXT, story_active INTEGER, is_private INTEGER,
  verified INTEGER NOT NULL DEFAULT 0, needs_verify INTEGER NOT NULL DEFAULT 0, verify_note TEXT,
  posts_visible INTEGER, followers INTEGER, bio TEXT, why TEXT,
  suggest_cleanup INTEGER NOT NULL DEFAULT 0, reviewed INTEGER NOT NULL DEFAULT 0,
  followed INTEGER NOT NULL DEFAULT 0, saved_count INTEGER NOT NULL DEFAULT 0,
  depth INTEGER NOT NULL DEFAULT 0, notes TEXT,
  first_seen TEXT, last_checked TEXT, next_check TEXT
);
CREATE INDEX IF NOT EXISTS acc_status ON accounts(status);
CREATE TABLE IF NOT EXISTS edges (parent TEXT NOT NULL, child TEXT NOT NULL, kind TEXT NOT NULL,
  PRIMARY KEY (parent, child, kind));
CREATE TABLE IF NOT EXISTS checks (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
  ts TEXT NOT NULL, result TEXT NOT NULL);
"""

FIELDS = {"status", "intent", "themes", "priority", "value_score", "posts_per_week", "last_post_at",
          "last_reel_at", "last_collab_at", "story_active", "is_private", "verified", "needs_verify",
          "verify_note", "posts_visible", "followers", "bio", "why", "suggest_cleanup", "reviewed",
          "followed", "saved_count", "depth", "notes", "first_seen", "last_checked", "next_check"}


def norm(username) -> str:
    return (username or "").strip().lstrip("@").strip().lower()


class SourcesDB:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(str(path))
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)

    def upsert(self, username, **fields) -> bool:
        u = norm(username)
        bad = set(fields) - FIELDS
        if bad:
            raise KeyError(f"unknown fields: {bad}")
        if not u:
            return False
        created = self.c.execute("SELECT 1 FROM accounts WHERE username=?", (u,)).fetchone() is None
        if created:
            self.c.execute("INSERT INTO accounts(username, first_seen) VALUES(?,?)",
                           (u, datetime.now().isoformat()))
        if fields:
            sets = ",".join(f"{k}=?" for k in fields)
            self.c.execute(f"UPDATE accounts SET {sets} WHERE username=?", (*fields.values(), u))
        self.c.commit()
        return created

    def update(self, username, **fields):
        self.upsert(username, **fields)

    def get(self, username):
        return self.c.execute("SELECT * FROM accounts WHERE username=?", (norm(username),)).fetchone()

    def by_status(self, status, limit=1000):
        return self.c.execute("SELECT * FROM accounts WHERE status=? LIMIT ?", (status, limit)).fetchall()

    def counts(self) -> dict[str, int]:
        return {r[0]: r[1] for r in self.c.execute("SELECT status, COUNT(*) FROM accounts GROUP BY status")}

    def add_edge(self, parent, child, kind):
        p, ch = norm(parent), norm(child)
        if p and ch:
            self.c.execute("INSERT OR IGNORE INTO edges(parent,child,kind) VALUES(?,?,?)", (p, ch, kind))
            self.c.commit()

    def log_check(self, username, result):
        self.c.execute("INSERT INTO checks(username,ts,result) VALUES(?,?,?)",
                       (norm(username), datetime.now().isoformat(), result))
        self.c.commit()

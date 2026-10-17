from __future__ import annotations

from datetime import datetime

from .activity import Activity, decide
from .db import SourcesDB


def flag_for_verification(sdb: SourcesDB, now: datetime, years: int = 2) -> int:
    cutoff = now.replace(year=now.year - years).strftime("%Y-%m-%d")
    rows = sdb.c.execute(
        "SELECT username, last_post_at, posts_visible FROM accounts "
        "WHERE followed=1 AND status!='personal' AND saved_count=0 AND reviewed=0 "
        "AND verified=0 AND needs_verify=0 AND suggest_cleanup=0").fetchall()
    n = 0
    for r in rows:
        why = None
        if r["last_post_at"] and r["last_post_at"][:10] < cutoff:
            why = f"по старым данным: последний пост {r['last_post_at'][:10]} (проверен один канал)"
        elif r["posts_visible"] == 0:
            why = "по старым данным: нет видимых постов (проверен один канал)"
        if why:
            sdb.update(r["username"], needs_verify=1, why=why)
            n += 1
    return n


def record_activity(sdb: SourcesDB, username: str, a: Activity, now: datetime, years: int = 2) -> str:
    verdict, why = decide(a, now, years)
    fields = dict(last_post_at=a.last_post, last_reel_at=a.last_reel, last_collab_at=a.last_collab,
                  story_active=int(a.story_active), is_private=int(a.private), last_checked=now.isoformat())
    if verdict == "active":
        fields.update(verified=1, needs_verify=0, suggest_cleanup=0, why=why)
    elif verdict == "inactive":
        fields.update(verified=1, needs_verify=0, suggest_cleanup=1, why=why)
    else:
        fields.update(verified=0, suggest_cleanup=0, verify_note=why, needs_verify=0 if a.private else 1)
    sdb.update(username, **fields)
    return verdict


def candidates(sdb: SourcesDB, limit: int = 10, offset: int = 0):
    return sdb.c.execute(
        "SELECT * FROM accounts WHERE suggest_cleanup=1 AND reviewed=0 "
        "ORDER BY (last_post_at IS NULL), last_post_at ASC, username LIMIT ? OFFSET ?",
        (limit, offset)).fetchall()


def marked(sdb: SourcesDB):
    return sdb.c.execute(
        "SELECT * FROM accounts WHERE intent='cleanup' AND followed=1 AND status!='ignored' "
        "ORDER BY (last_post_at IS NULL), last_post_at ASC, username").fetchall()

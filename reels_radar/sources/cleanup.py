from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .activity import Activity, decide
from .db import SourcesDB


def flag_for_verification(sdb: SourcesDB, now: datetime, years: int = 2) -> int:
    from .activity import _cutoff
    cutoff = _cutoff(now, years)
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
    row = sdb.get(username)
    protected = row is not None and (row["status"] in ("personal", "ignored") or row["saved_count"] > 0 or not row["followed"])
    fields = dict(last_post_at=a.last_post, last_reel_at=a.last_reel, last_collab_at=a.last_collab,
                  story_active=int(a.story_active), is_private=int(a.private), last_checked=now.isoformat())
    if verdict == "active":
        fields.update(verified=1, needs_verify=0, suggest_cleanup=0, why=why)
    elif verdict == "inactive":
        fields.update(verified=1, needs_verify=0, suggest_cleanup=0 if protected else 1,
                      why=why + (" (защищён: личный, с сохранёнками или уже отписан)" if protected else ""))
    else:
        fields.update(verified=0, suggest_cleanup=0, verify_note=why, needs_verify=0 if a.private else 1)
    sdb.update(username, **fields)
    return verdict


def candidates(sdb: SourcesDB, limit: int = 10, offset: int = 0):
    return sdb.c.execute(
        "SELECT * FROM accounts WHERE suggest_cleanup=1 AND reviewed=0 AND followed=1 AND saved_count=0 "
        "AND status NOT IN ('personal', 'ignored') "
        "ORDER BY (last_post_at IS NULL), last_post_at ASC, username LIMIT ? OFFSET ?",
        (limit, offset)).fetchall()


def marked(sdb: SourcesDB):
    return sdb.c.execute(
        "SELECT * FROM accounts WHERE intent='cleanup' AND followed=1 AND status!='ignored' "
        "ORDER BY (last_post_at IS NULL), last_post_at ASC, username").fetchall()


def apply_action(sdb: SourcesDB, username: str, action: str) -> str:
    r = sdb.get(username)
    if r is None:
        return "аккаунт не найден"
    if r["status"] == "ignored":
        return "уже отписан"
    if action == "del":
        sdb.update(username, intent="cleanup", reviewed=1)
        return "на удаление"
    if action == "keep":
        sdb.update(username, intent="none", reviewed=1, suggest_cleanup=0)
        return "оставлен"
    if action == "personal":
        sdb.update(username, status="personal", intent="none", reviewed=1, suggest_cleanup=0)
        return "личный"
    if action == "done":
        sdb.update(username, status="ignored", followed=0)
        return "отписан"
    raise ValueError(f"unknown action {action}")


def export_cleanup(sdb: SourcesDB, path) -> int:
    rows = marked(sdb)
    lines = [f"{r['username']} - {r['why'] or 'без причины'}" for r in rows]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines).replace("—", "-") + ("\n" if lines else ""), encoding="utf8")
    return len(rows)

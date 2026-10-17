from __future__ import annotations

import random
import time
from datetime import datetime

from .cleanup import record_activity
from .db import SourcesDB

STOP = {"RATE", "LOGIN", "CHALLENGE"}


def verify_batch(sdb: SourcesDB, reader, now: datetime, years: int = 2, limit: int = 20,
                 sleep=time.sleep, pause=(1.0, 2.5)) -> dict:
    rows = sdb.c.execute(
        "SELECT username FROM accounts WHERE needs_verify=1 AND followed=1 AND status!='personal' "
        "ORDER BY (last_post_at IS NULL), last_post_at ASC, username LIMIT ?", (limit,)).fetchall()
    res = {"active": 0, "inactive": 0, "unknown": 0, "stopped": None}
    for r in rows:
        u = r["username"]
        a = reader(u)
        sdb.log_check(u, a.error or "ok")
        if a.error in STOP:
            res["stopped"] = a.error
            break
        res[record_activity(sdb, u, a, now, years)] += 1
        sleep(random.uniform(*pause))
    return res

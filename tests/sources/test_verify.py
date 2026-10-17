from datetime import datetime
from reels_radar.sources.activity import Activity, CHANNELS
from reels_radar.sources.verify import verify_batch

NOW = datetime(2026, 10, 17)
ALL = frozenset(CHANNELS)
OLD = "2019-03-01T00:00:00.000Z"


def seed(sdb, *names):
    for n in names:
        sdb.upsert(n, followed=1, needs_verify=1, last_post_at=OLD, posts_visible=1)


def test_verify_batch_classifies_and_logs(sdb):
    seed(sdb, "dead", "reeler")
    def reader(u):
        return Activity(last_post=OLD, last_reel="2026-09-01T00:00:00.000Z" if u == "reeler" else None, channels=ALL)
    res = verify_batch(sdb, reader, NOW, limit=10, sleep=lambda s: None)
    assert res["active"] == 1 and res["inactive"] == 1
    assert sdb.get("dead")["suggest_cleanup"] == 1 and sdb.get("reeler")["suggest_cleanup"] == 0
    assert sdb.c.execute("select count(*) from checks").fetchone()[0] == 2


def test_verify_batch_stops_on_rate_limit_and_keeps_rest(sdb):
    seed(sdb, "a", "b", "c")
    calls = []
    def reader(u):
        calls.append(u)
        return Activity(error="RATE", channels=ALL) if len(calls) == 2 else Activity(last_post=OLD, channels=ALL)
    res = verify_batch(sdb, reader, NOW, limit=10, sleep=lambda s: None)
    assert res["stopped"] == "RATE" and len(calls) == 2
    assert sdb.get("c")["needs_verify"] == 1 and sdb.get("c")["verified"] == 0


def test_verify_batch_respects_limit_and_skips_personal(sdb):
    seed(sdb, "a", "b", "c")
    sdb.update("a", status="personal")
    seen = []
    def reader(u):
        seen.append(u); return Activity(last_post=OLD, channels=ALL)
    verify_batch(sdb, reader, NOW, limit=1, sleep=lambda s: None)
    assert len(seen) == 1 and "a" not in seen

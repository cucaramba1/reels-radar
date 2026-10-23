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


def test_verify_skips_accounts_that_became_saved(sdb):
    seed(sdb, "a", "b")
    sdb.update("a", saved_count=2)
    seen = []
    def reader(u):
        seen.append(u); return Activity(last_post=OLD, channels=ALL)
    verify_batch(sdb, reader, NOW, limit=10, sleep=lambda s: None)
    assert seen == ["b"]


def test_any_unknown_error_stops_batch_but_not_found_continues(sdb):
    seed(sdb, "a", "b", "c")
    calls = []
    def reader(u):
        calls.append(u)
        return {"a": Activity(error="NOT_FOUND"), "b": Activity(error="429 too many")}.get(u, Activity(last_post=OLD, channels=ALL))
    res = verify_batch(sdb, reader, NOW, limit=10, sleep=lambda s: None)
    assert calls == ["a", "b"] and res["stopped"] == "429 too many"


def test_chronically_failing_accounts_go_last(sdb):
    seed(sdb, "bad", "good")
    for _ in range(3):
        sdb.log_check("bad", "NOT_FOUND")
    sdb.update("bad", last_post_at="2010-01-01T00:00:00.000Z")
    seen = []
    def reader(u):
        seen.append(u); return Activity(last_post=OLD, channels=ALL)
    verify_batch(sdb, reader, NOW, limit=1, sleep=lambda s: None)
    assert seen == ["good"]


def test_budget_left_counts_today_only(sdb):
    from reels_radar.sources.verify import budget_left
    sdb.log_check("a", "ok"); sdb.log_check("b", "ok")
    sdb.c.execute("INSERT INTO checks(username,ts,result) VALUES('c','2020-01-01T00:00:00','ok')"); sdb.c.commit()
    assert budget_left(sdb, 5, datetime.now()) == 3
    assert budget_left(sdb, 1, datetime.now()) == 0

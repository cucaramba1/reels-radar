from reels_radar.sources.db import norm


def test_norm():
    assert norm("@Some.User ") == "some.user"
    assert norm(None) == ""


def test_upsert_creates_then_updates(sdb):
    assert sdb.upsert("@Bob", followed=1) is True
    assert sdb.upsert("bob", themes="ИИ") is False
    r = sdb.get("BOB")
    assert r["followed"] == 1 and r["themes"] == "ИИ" and r["status"] == "candidate" and r["intent"] == "none"


def test_empty_username_ignored(sdb):
    assert sdb.upsert("", followed=1) is False
    assert sdb.upsert(None, followed=1) is False
    assert sdb.counts() == {}


def test_unknown_field_rejected(sdb):
    import pytest
    with pytest.raises(KeyError):
        sdb.upsert("a", bogus=1)


def test_activity_fields_exist(sdb):
    sdb.upsert("a", last_reel_at="2026-01-01", last_collab_at="2026-02-01", story_active=1, is_private=0,
               verified=1, needs_verify=0, verify_note="x")
    r = sdb.get("a")
    assert r["last_reel_at"] == "2026-01-01" and r["story_active"] == 1


def test_edges_and_checks(sdb):
    sdb.upsert("a"); sdb.upsert("b")
    sdb.add_edge("a", "b", "similar"); sdb.add_edge("a", "b", "similar")
    assert sdb.c.execute("select count(*) from edges").fetchone()[0] == 1
    sdb.log_check("a", "ok")
    assert sdb.c.execute("select count(*) from checks").fetchone()[0] == 1

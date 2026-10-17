from reels_radar.sources.cleanup import apply_action, export_cleanup
from reels_radar.sources.cards import account_text, account_keyboard, parse_account_cb


def acc(sdb, u, **kw):
    sdb.upsert(u, followed=1, last_post_at="2019-03-01T00:00:00.000Z", posts_visible=1, **kw)


def test_del_then_keep_last_wins(sdb):
    acc(sdb, "a")
    apply_action(sdb, "a", "del"); apply_action(sdb, "a", "del")
    assert sdb.get("a")["intent"] == "cleanup" and sdb.get("a")["reviewed"] == 1
    apply_action(sdb, "a", "keep")
    assert sdb.get("a")["intent"] == "none"


def test_personal_blocks_cleanup(sdb):
    acc(sdb, "a")
    apply_action(sdb, "a", "personal")
    r = sdb.get("a")
    assert r["status"] == "personal" and r["intent"] == "none" and r["suggest_cleanup"] == 0


def test_done_is_final(sdb):
    acc(sdb, "a")
    apply_action(sdb, "a", "del"); apply_action(sdb, "a", "done")
    r = sdb.get("a")
    assert r["status"] == "ignored" and r["followed"] == 0
    apply_action(sdb, "a", "keep")
    assert sdb.get("a")["status"] == "ignored"


def test_export_cleanup(tmp_path, sdb):
    acc(sdb, "alpha", why="последний пост 2019-03-01"); acc(sdb, "beta")
    apply_action(sdb, "alpha", "del")
    p = tmp_path / "cleanup.txt"
    assert export_cleanup(sdb, p) == 1
    text = p.read_text()
    assert "alpha" in text and "2019-03-01" in text and "beta" not in text and "—" not in text


def test_callback_roundtrip_with_dots_and_underscores():
    for u in ("john.doe_99", "a" * 30, "x.y.z"):
        for _, data in account_keyboard(u)[0]:
            action, name = parse_account_cb(data)
            assert name == u and action in {"del", "keep", "personal"}
            assert len(data.encode()) <= 64


def test_account_text(sdb):
    acc(sdb, "a", why="последний пост 2019-03-01")
    t = account_text(sdb.get("a"))
    assert "@a" in t and "2019-03-01" in t and "—" not in t

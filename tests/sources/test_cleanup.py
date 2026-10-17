from datetime import datetime
from reels_radar.sources.activity import Activity, CHANNELS, decide
from reels_radar.sources.cleanup import flag_for_verification, record_activity, candidates, marked

NOW = datetime(2026, 10, 17)
ALL = frozenset(CHANNELS)
OLD = "2019-03-01T00:00:00.000Z"
NEW = "2026-09-01T00:00:00.000Z"


def acc(sdb, u, **kw):
    sdb.upsert(u, followed=1, **kw)


def test_decide_active_by_any_single_channel():
    assert decide(Activity(last_post=OLD, last_reel=NEW, channels=ALL), NOW, 2)[0] == "active"
    assert decide(Activity(last_post=OLD, last_collab=NEW, channels=ALL), NOW, 2)[0] == "active"
    assert decide(Activity(last_post=OLD, story_active=True, channels=ALL), NOW, 2)[0] == "active"
    assert decide(Activity(last_reel=NEW, channels=frozenset({"reels"})), NOW, 2)[0] == "active"


def test_decide_inactive_only_when_all_channels_checked_and_old():
    a = Activity(last_post=OLD, last_reel=OLD, last_collab=None, story_active=False, channels=ALL)
    assert decide(a, NOW, 2)[0] == "inactive"
    partial = Activity(last_post=OLD, channels=frozenset({"posts"}))
    assert decide(partial, NOW, 2)[0] == "unknown"


def test_decide_private_and_error_are_unknown():
    assert decide(Activity(private=True, channels=ALL), NOW, 2)[0] == "unknown"
    assert decide(Activity(error="RATE", channels=ALL), NOW, 2)[0] == "unknown"


def test_decide_no_content_anywhere_needs_proof():
    assert decide(Activity(channels=ALL, posts_count=0), NOW, 2)[0] == "inactive"


def test_legacy_data_flags_but_never_suggests(sdb):
    acc(sdb, "old", last_post_at=OLD, posts_visible=1)
    acc(sdb, "empty", posts_visible=0)
    acc(sdb, "fresh", last_post_at=NEW, posts_visible=1)
    assert flag_for_verification(sdb, NOW) == 2
    assert sdb.get("old")["needs_verify"] == 1 and sdb.get("old")["suggest_cleanup"] == 0
    assert sdb.get("fresh")["needs_verify"] == 0


def test_protected_accounts_not_flagged(sdb):
    acc(sdb, "saved", last_post_at=OLD, posts_visible=1, saved_count=2)
    acc(sdb, "friend", last_post_at=OLD, posts_visible=1, status="personal")
    acc(sdb, "keeper", last_post_at=OLD, posts_visible=1, reviewed=1)
    sdb.upsert("x", followed=0, last_post_at=OLD, posts_visible=1)
    assert flag_for_verification(sdb, NOW) == 0


def test_reels_only_account_is_not_suggested(sdb):
    acc(sdb, "reeler", last_post_at=OLD, posts_visible=1)
    flag_for_verification(sdb, NOW)
    verdict = record_activity(sdb, "reeler", Activity(last_post=OLD, last_reel=NEW, channels=ALL), NOW)
    r = sdb.get("reeler")
    assert verdict == "active" and r["suggest_cleanup"] == 0 and r["needs_verify"] == 0 and r["last_reel_at"] == NEW


def test_stories_only_account_is_not_suggested(sdb):
    acc(sdb, "storyteller", last_post_at=OLD, posts_visible=1)
    assert record_activity(sdb, "storyteller", Activity(last_post=OLD, story_active=True, channels=ALL), NOW) == "active"
    assert sdb.get("storyteller")["suggest_cleanup"] == 0


def test_truly_dead_account_is_suggested_with_all_channels_in_why(sdb):
    acc(sdb, "dead", last_post_at=OLD, posts_visible=1)
    assert record_activity(sdb, "dead", Activity(last_post=OLD, last_reel=OLD, channels=ALL), NOW) == "inactive"
    r = sdb.get("dead")
    assert r["suggest_cleanup"] == 1 and r["verified"] == 1 and "2019-03-01" in r["why"] and "истори" in r["why"]


def test_private_and_incomplete_are_unknown_not_suggested(sdb):
    acc(sdb, "priv", posts_visible=0)
    acc(sdb, "half", last_post_at=OLD, posts_visible=1)
    assert record_activity(sdb, "priv", Activity(private=True, channels=ALL), NOW) == "unknown"
    assert record_activity(sdb, "half", Activity(last_post=OLD, channels=frozenset({"posts"})), NOW) == "unknown"
    assert sdb.get("priv")["suggest_cleanup"] == 0 and sdb.get("priv")["verify_note"]
    assert sdb.get("half")["suggest_cleanup"] == 0 and sdb.get("half")["needs_verify"] == 1


def test_candidates_order_and_marked(sdb):
    for u, d in (("b", "2020-01-01T00:00:00.000Z"), ("a", "2018-01-01T00:00:00.000Z")):
        acc(sdb, u, last_post_at=d, posts_visible=1)
        record_activity(sdb, u, Activity(last_post=d, channels=ALL), NOW)
    assert [r["username"] for r in candidates(sdb, 10)] == ["a", "b"]
    assert [r["username"] for r in candidates(sdb, 1, offset=1)] == ["b"]
    sdb.update("a", intent="cleanup")
    assert [r["username"] for r in marked(sdb)] == ["a"]


def test_empty_snapshot_without_proof_is_unknown_not_inactive():
    assert decide(Activity(channels=ALL), NOW, 2)[0] == "unknown"
    assert decide(Activity(channels=ALL, posts_count=0), NOW, 2)[0] == "inactive"


def test_unparseable_date_is_unknown():
    assert decide(Activity(last_post="01.03.2026", channels=ALL), NOW, 2)[0] == "unknown"
    assert decide(Activity(last_post="2026-03-01", channels=ALL), NOW, 2)[0] == "active"


def test_candidates_never_include_saved_personal_or_unfollowed(sdb):
    for u in ("saved", "friend", "gone", "ok"):
        acc(sdb, u, last_post_at=OLD, posts_visible=1, suggest_cleanup=1)
    sdb.update("saved", saved_count=3); sdb.update("friend", status="personal"); sdb.update("gone", followed=0)
    assert [r["username"] for r in candidates(sdb, 10)] == ["ok"]


def test_record_activity_does_not_suggest_protected(sdb):
    acc(sdb, "friend", last_post_at=OLD, posts_visible=1, status="personal")
    acc(sdb, "saved", last_post_at=OLD, posts_visible=1, saved_count=2)
    for u in ("friend", "saved"):
        record_activity(sdb, u, Activity(last_post=OLD, channels=ALL), NOW)
        assert sdb.get(u)["suggest_cleanup"] == 0

import time
from reels_radar.sources.activity import CHANNELS
from reels_radar.sources.profile_parse import build_activity, classify_page, parse_meta, parse_timeline

KEY = "xdt_api__v1__feed__user_timeline_graphql_connection"


def ts(y, m, d):
    return int(time.mktime(time.strptime(f"{y}-{m}-{d} 12", "%Y-%m-%d %H")))


def resp(*nodes):
    return {"data": {KEY: {"edges": [{"node": n} for n in nodes]}}}


def test_parse_timeline_types_and_collab():
    r = resp({"taken_at": ts(2018, 1, 1), "product_type": "feed"},
             {"taken_at": ts(2026, 4, 7), "product_type": "clips", "coauthor_producers": [{"username": "x"}]})
    nodes = parse_timeline([r])
    assert [n.product_type for n in nodes] == ["feed", "clips"]
    assert [n.collab for n in nodes] == [False, True]


def test_parse_timeline_ignores_foreign_and_broken():
    assert parse_timeline([{"data": {"xdt_api__v1__feed__timeline__connection": {"edges": []}}}, {}, None]) == []
    assert parse_timeline([resp({"product_type": "feed"})]) == []  # без taken_at


def test_parse_meta():
    assert parse_meta("198K Followers, 4,057 Following, 2,895 Posts - See photos") == (198000, 4057, 2895)
    assert parse_meta("1.2M Followers, 10 Following, 0 Posts") == (1200000, 10, 0)
    assert parse_meta("мусор") == (None, None, None)
    assert parse_meta(None) == (None, None, None)


def test_classify_page():
    assert classify_page("This account is private") == "private"
    assert classify_page("Sorry, this page isn't available.") == "not_found"
    assert classify_page("mikhnesss 2,895 posts") == "ok"


def test_build_activity_takes_max_over_pinned():
    nodes = parse_timeline([resp(
        {"taken_at": ts(2016, 1, 1), "product_type": "feed"},
        {"taken_at": ts(2026, 4, 7), "product_type": "carousel_container"},
        {"taken_at": ts(2026, 9, 1), "product_type": "clips"},
        {"taken_at": ts(2026, 10, 1), "product_type": "feed", "coauthor_producers": [{"username": "x"}]})])
    a = build_activity(nodes, 50, ring=False, status="ok")
    assert a.last_post.startswith("2026-04-07")
    assert a.last_reel.startswith("2026-09-01")
    assert a.last_collab.startswith("2026-10-01")
    assert a.channels == frozenset(CHANNELS) and a.error is None


def test_build_activity_empty_profile_confirmed():
    a = build_activity([], 0, ring=False, status="ok")
    assert a.posts_count == 0 and a.channels == frozenset(CHANNELS)


def test_build_activity_no_timeline_is_not_complete():
    a = build_activity([], 12, ring=False, status="ok")
    assert a.error == "NO_TIMELINE" and not a.channels
    a = build_activity([], None, ring=False, status="ok")
    assert a.error == "NO_TIMELINE"


def test_build_activity_private_and_gone():
    assert build_activity([], 5, ring=False, status="private").private is True
    assert build_activity([], None, ring=False, status="not_found").error == "NOT_FOUND"


def test_build_activity_story_ring():
    a = build_activity(parse_timeline([resp({"taken_at": ts(2019, 1, 1), "product_type": "feed"})]), 3, ring=True, status="ok")
    assert a.story_active is True

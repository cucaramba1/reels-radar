import json
from reels_radar.sources.importers import import_following, import_saved_authors, import_last_posts


def write(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False))


def test_import_following_dedups_case_and_empty(tmp_path, sdb):
    f = tmp_path / "following.json"
    write(f, {"relationships_following": [
        {"title": "Bob", "string_list_data": [{"timestamp": 1}]},
        {"title": "bob"}, {"title": ""}, {"nope": 1}, {"title": "alice"}]})
    assert import_following(sdb, f) == 2
    assert sdb.get("bob")["followed"] == 1
    assert import_following(sdb, f) == 0


def test_reimport_keeps_manual_marks(tmp_path, sdb):
    f = tmp_path / "following.json"
    write(f, {"relationships_following": [{"title": "bob"}]})
    import_following(sdb, f)
    sdb.update("bob", reviewed=1, intent="cleanup", status="personal")
    import_following(sdb, f)
    r = sdb.get("bob")
    assert r["reviewed"] == 1 and r["intent"] == "cleanup" and r["status"] == "personal"


def test_import_saved_authors_counts_and_top_theme(tmp_path, sdb):
    ik, tm = tmp_path / "ik.json", tmp_path / "tm.json"
    write(ik, {"001": {"author": "Carol"}, "002": {"author": "carol"}, "003": {"author": "carol"}, "004": {"author": "dave"}, "005": {}})
    write(tm, {"001": "ИИ", "002": "Карьера", "003": "ИИ", "004": "Вьетнам"})
    exp = tmp_path / "exp"; exp.mkdir()
    assert import_saved_authors(sdb, ik, tm, exp) == 2
    c = sdb.get("carol")
    assert c["saved_count"] == 3 and c["themes"] == "ИИ"
    assert import_saved_authors(sdb, ik, tm, exp) == 0
    assert sdb.get("carol")["saved_count"] == 3


def test_import_last_posts(tmp_path, sdb):
    j = tmp_path / "lp.jsonl"
    j.write_text('{"u":"Bob","lastPost":"2019-03-01T10:00:00.000Z"}\n'
                 '{"u":"empty","lastPost":null,"note":"no_posts_found_or_private"}\n\nnot json\n')
    assert import_last_posts(sdb, j) == 2
    assert sdb.get("bob")["last_post_at"].startswith("2019-03-01") and sdb.get("bob")["posts_visible"] == 1
    assert sdb.get("empty")["posts_visible"] == 0 and sdb.get("empty")["last_post_at"] is None

def test_add_item_is_idempotent(db):
    assert db.add_item("AAA", "https://i/reel/AAA/", "cap", 100) is True
    assert db.add_item("AAA", "https://i/reel/AAA/", "cap", 100) is False
    assert db.get("AAA")["status"] == "new"


def test_update_and_by_status(db):
    db.add_item("AAA", "u", "c", 1)
    db.update("AAA", status="local", score=55.0, transcript="текст")
    assert [r["code"] for r in db.by_status("local")] == ["AAA"]
    assert db.get("AAA")["score"] == 55.0
    assert db.counts() == {"local": 1}


def test_kv(db):
    assert db.kv_get("x", "d") == "d"
    db.kv_set("x", "1")
    assert db.kv_get("x") == "1"

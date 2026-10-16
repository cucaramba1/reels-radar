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


def test_owner_column_and_migration(tmp_path):
    import sqlite3
    from reels_radar.db import DB
    p = tmp_path / "old.db"
    c = sqlite3.connect(p)
    c.executescript("CREATE TABLE items (code TEXT PRIMARY KEY, url TEXT NOT NULL, caption TEXT NOT NULL DEFAULT '', "
                    "ts INTEGER NOT NULL DEFAULT 0, folder TEXT, status TEXT NOT NULL DEFAULT 'new', "
                    "attempts INTEGER NOT NULL DEFAULT 0, fail_reason TEXT, ocr_text TEXT, transcript TEXT, score REAL, "
                    "theme TEXT, purposes TEXT, kind TEXT, summary TEXT, template TEXT, title TEXT, body TEXT, "
                    "note_path TEXT, note_created INTEGER, moc_line TEXT, updated TEXT NOT NULL DEFAULT '');")
    c.commit(); c.close()
    db = DB(p)
    db.add_item("A", "u", "c", 1, owner="bob")
    assert db.get("A")["owner"] == "bob"

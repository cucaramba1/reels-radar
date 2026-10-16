from reels_radar.config import Theme
from reels_radar.review import save_verdict, apply_action
from reels_radar.vault import rollback
from reels_radar.vision import Verdict

THEMES = {"ИИ": Theme("ИИ", "ИИ работа", "m.md"), "Разное": Theme("Разное", "Разное", "r.md")}


def v(purposes, skip=False):
    return Verdict("ИИ", purposes, "знание", "суть", "", "Заг", "тело", skip, "")


def test_skip_goes_to_archive(db):
    db.add_item("A", "u", "", 1)
    save_verdict(db, "A", v(["note"], skip=True))
    assert db.get("A")["status"] == "archived"


def test_ok_note_writes_file(db, tmp_path):
    db.add_item("A", "u", "", 1)
    save_verdict(db, "A", v(["note"]))
    apply_action(db, "A", "ok", THEMES, tmp_path)
    r = db.get("A")
    assert r["status"] == "written" and (tmp_path / r["note_path"]).exists()


def test_ok_friend_only_writes_nothing(db, tmp_path):
    db.add_item("A", "u", "", 1)
    save_verdict(db, "A", v(["friend"]))
    apply_action(db, "A", "ok", THEMES, tmp_path)
    assert db.get("A")["status"] == "approved" and not list(tmp_path.iterdir())


def test_no_rejects_and_theme_change(db, tmp_path):
    db.add_item("A", "u", "", 1)
    save_verdict(db, "A", v(["note"]))
    apply_action(db, "A", "set_theme:Разное", THEMES, tmp_path)
    assert db.get("A")["theme"] == "Разное"
    apply_action(db, "A", "no", THEMES, tmp_path)
    assert db.get("A")["status"] == "rejected"


def test_rollback_moves_to_trash_and_cleans_moc(db, tmp_path):
    db.add_item("A", "u", "", 1)
    save_verdict(db, "A", v(["note"]))
    apply_action(db, "A", "ok", THEMES, tmp_path)
    rel = db.get("A")["note_path"]
    rollback(tmp_path, db, "A", THEMES)
    assert not (tmp_path / rel).exists() and (tmp_path / ".trash" / rel).exists()
    assert "[[Заг]]" not in (tmp_path / "ИИ работа" / "m.md").read_text()
    assert db.get("A")["status"] == "draft"

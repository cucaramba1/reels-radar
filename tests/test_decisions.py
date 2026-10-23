import json

import pytest

from reels_radar.config import Theme
from reels_radar.decisions import (CONTENT, find_section, proposed, reject, sec_hash, undo, write_idea,
                                   write_inspiration, write_note_to, new_section)
from reels_radar.review import save_verdict
from reels_radar.vault import catalog
from reels_radar.vision import Verdict

AI = Theme("ИИ", "ИИ работа", "ИИ работа — карта заметок.md")
THEMES = {"ИИ": AI, "Съёмка и монтаж": CONTENT, "Юмор": Theme("Юмор", None, None)}


def mkcanvas(root, folder, moc):
    (root / folder).mkdir(parents=True)
    (root / folder / moc).write_text(f"# {folder}\n\n")
    (root / f"{folder}.canvas").write_text(json.dumps({"nodes": [
        {"id": "m", "type": "file", "file": f"{folder}/{moc}", "x": 0, "y": 0, "width": 400, "height": 200}], "edges": []}))


@pytest.fixture
def vault(tmp_path):
    mkcanvas(tmp_path, "ИИ работа", "ИИ работа — карта заметок.md")
    mkcanvas(tmp_path, "Контент и соцсети", "Контент и соцсети — карта заметок.md")
    mkcanvas(tmp_path, "Маркетинг", "Маркетинг — карта заметок.md")
    return tmp_path


def card(db, code="A", theme="ИИ"):
    db.add_item(code, "u", "", 1)
    save_verdict(db, code, Verdict(theme, ["note", "content"], "знание", "суть", "хук 0-3с", "Заг", "тело", False, ""))


def nodes(vault, name):
    return [n.get("file") for n in json.loads((vault / f"{name}.canvas").read_text())["nodes"]]


def test_note_to_proposed_section_and_undo(db, vault):
    card(db)
    sec = proposed(catalog(vault, THEMES), db.get("A"))
    assert sec.folder == "ИИ работа"
    write_note_to(db, "A", sec, vault)
    r = db.get("A")
    assert r["status"] == "written" and r["decision"] == "note:ИИ работа" and (vault / r["note_path"]).exists()
    assert r["note_path"] in nodes(vault, "ИИ работа")
    undo(db, "A", vault, THEMES)
    assert db.get("A")["status"] == "draft" and db.get("A")["decision"] is None
    assert r["note_path"] not in nodes(vault, "ИИ работа")
    assert (vault / ".trash" / r["note_path"]).exists()


def test_catalog_finds_canvases_not_in_themes(vault):
    folders = [t.folder for t in catalog(vault, THEMES)]
    assert "Маркетинг" in folders and folders.count("ИИ работа") == 1
    assert find_section(catalog(vault, THEMES), sec_hash(AI)).folder == "ИИ работа"


def test_idea_creates_section_with_canvas_and_links(db, vault):
    card(db)
    write_idea(db, "A", vault)
    r = db.get("A")
    assert r["decision"] == "idea" and r["note_path"].startswith("Контент и соцсети/Идеи для рилсов/")
    text = (vault / r["note_path"]).read_text()
    assert "Структура рилса" in text and "хук 0-3с" in text
    assert "[[Идеи для рилсов — карта заметок]]" in (vault / "Контент и соцсети/Контент и соцсети — карта заметок.md").read_text()
    assert (vault / "Идеи для рилсов.canvas").exists() and r["note_path"] in nodes(vault, "Идеи для рилсов")
    assert "Контент и соцсети/Идеи для рилсов/Идеи для рилсов — карта заметок.md" in nodes(vault, "Контент и соцсети")


def test_inspiration_three_subcanvases(db, vault):
    card(db, "A"); card(db, "B"); card(db, "C")
    write_inspiration(db, "A", "visual", vault)
    write_inspiration(db, "B", "memes", vault)
    write_inspiration(db, "C", "ideas", vault)
    for n in ("Вдохновение", "Вдохновение — визуал", "Вдохновение — мемы", "Вдохновение — идеи"):
        assert (vault / f"{n}.canvas").exists()
    assert db.get("B")["decision"] == "inspo:memes"
    assert db.get("A")["note_path"] in nodes(vault, "Вдохновение — визуал")


def test_new_section_with_intro(db, vault):
    card(db, "A", "Юмор")
    write_note_to(db, "A", new_section("Мемы и юмор"), vault, "Смешное и мемы")
    assert (vault / "Мемы и юмор.canvas").exists()
    assert "Смешное и мемы" in (vault / "Мемы и юмор/Мемы и юмор — карта заметок.md").read_text()
    assert db.get("A")["status"] == "written"


def test_reject_and_undo_without_note(db, vault):
    card(db)
    reject(db, "A", "friend")
    assert db.get("A")["status"] == "rejected" and db.get("A")["decision"] == "friend"
    undo(db, "A", vault, THEMES)
    assert db.get("A")["status"] == "draft"


def test_double_decision_ignored(db, vault):
    card(db)
    write_idea(db, "A", vault)
    assert write_idea(db, "A", vault) == "уже обработано"

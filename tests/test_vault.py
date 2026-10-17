from reels_radar.config import Theme
from reels_radar.vault import safe_title, write_note, add_moc_line

T = Theme("ИИ", "ИИ работа", "ИИ работа — карта заметок.md")


def test_safe_title():
    assert safe_title('A/B: "тест"?') == "AB тест"
    assert len(safe_title("x" * 200)) == 80


def test_write_note_never_overwrites(tmp_path):
    p1, c1 = write_note(tmp_path, T, "Заголовок", "тело", "AAA")
    p2, c2 = write_note(tmp_path, T, "Заголовок", "другое", "BBB")
    assert p1 != p2 and c1 and c2
    assert "тело" in p1.read_text() and "другое" in p2.read_text()
    assert p2.parent == tmp_path / "ИИ работа"


def test_moc_line_appended_once(tmp_path):
    (tmp_path / "ИИ работа").mkdir()
    moc = tmp_path / "ИИ работа" / T.moc
    moc.write_text("# MOC\n")
    add_moc_line(tmp_path, T, "Заголовок")
    add_moc_line(tmp_path, T, "Заголовок")
    assert moc.read_text().count("[[Заголовок]]") == 1


def test_note_has_heading_and_related_section(tmp_path):
    p, _ = write_note(tmp_path, T, "Заголовок", "тело", "AAA")
    text = p.read_text()
    assert text.startswith("# Заголовок\n") and "## Связанные заметки" in text and "[[ИИ работа — карта заметок]]" in text


def test_add_to_canvas_adds_file_node_and_edge(tmp_path):
    import json
    from reels_radar.vault import add_to_canvas
    (tmp_path / "ИИ работа").mkdir()
    cv = tmp_path / "ИИ работа.canvas"
    cv.write_text(json.dumps({"nodes": [
        {"id": "m", "type": "file", "file": "ИИ работа/ИИ работа — карта заметок.md", "x": 0, "y": 0, "width": 400, "height": 200}],
        "edges": []}))
    add_to_canvas(tmp_path, T, "ИИ работа/Заголовок.md")
    add_to_canvas(tmp_path, T, "ИИ работа/Заголовок.md")  # идемпотентно
    d = json.loads(cv.read_text())
    files = [n for n in d["nodes"] if n.get("file") == "ИИ работа/Заголовок.md"]
    assert len(files) == 1 and files[0]["y"] >= 200
    assert any(e["fromNode"] == "m" and e["toNode"] == files[0]["id"] for e in d["edges"])


def test_add_to_canvas_missing_canvas_is_noop(tmp_path):
    from reels_radar.vault import add_to_canvas
    assert add_to_canvas(tmp_path, T, "ИИ работа/X.md") is False

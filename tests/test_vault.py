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

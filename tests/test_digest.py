from reels_radar.digest import build_digest


def add(db, code, status, purposes, theme, score, summary="суть", template=""):
    db.add_item(code, f"https://i/reel/{code}/", "", 1)
    db.update(code, status=status, purposes=purposes, theme=theme, score=score, summary=summary,
              template=template, title=code)


def test_digest_blocks(db):
    add(db, "A", "draft", "content", "Съёмка и монтаж", 90, "хук 3 сек", "шаблон А")
    add(db, "B", "draft", "claude,note", "ИИ", 70)
    add(db, "C", "draft", "note", "Слова и фразы", 50, "фраза")
    db.add_item("D", "https://i/reel/D/", "", 1); db.update("D", status="no_video", attempts=1)
    text = build_digest(db, "2000-01-01")
    assert "шаблон А" in text and "Нужен файл" in text and "https://i/reel/D/" in text and "—" not in text


def test_empty_blocks_omitted(db):
    assert "Нужен файл" not in build_digest(db, "2000-01-01")


def test_digest_folders_repeat_and_ytdlp(db):
    for c, folder in (("W1", "ИИ работа"), ("W2", "ИИ работа"), ("W3", "Монтаж")):
        add(db, c, "written", "note", "ИИ", 50)
        db.update(c, note_path=f"{folder}/{c}.md")
    add(db, "OLD", "written", "note", "ИИ", 50)
    db.update("OLD", note_path="ИИ работа/OLD.md")
    db.c.execute("UPDATE items SET updated='2020-01-01' WHERE code='OLD'"); db.c.commit()
    text = build_digest(db, "2026-01-01", mark_repeat=True, ytdlp_version="2020.01.01")
    assert "- ИИ работа: 2 (W1, W2)" in text or "- ИИ работа: 2 (W2, W1)" in text
    assert "- Монтаж: 1 (W3)" in text and "«OLD»" in text and "brew upgrade yt-dlp" in text
    assert "«OLD»" not in build_digest(db, "2026-01-01")  # уже повторяли
    from datetime import date
    assert "yt-dlp" not in build_digest(db, "2026-01-01", ytdlp_version=date.today().strftime("%Y.%m.%d"))

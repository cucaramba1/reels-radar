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

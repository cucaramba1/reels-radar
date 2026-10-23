from reels_radar.cards import render_card, keyboard_spec, parse_callback


def test_callback_roundtrip():
    for label, data in keyboard_spec("AAA")[0]:
        assert parse_callback(data)[1] == "AAA"


def test_card_has_no_long_dash(db):
    db.add_item("A", "https://i/reel/A/", "", 1)
    db.update("A", theme="ИИ", purposes="claude,note", kind="фича", summary="суть — вот", template="шаблон")
    text = render_card(db.get("A"))
    assert "—" not in text and "ИИ" in text and "суть" in text


def test_callbacks_fit_telegram_limit():
    from reels_radar.cards import section_cb
    assert len(section_cb("abcdef", "A" * 11).encode()) <= 64
    for row in keyboard_spec("A" * 11):
        assert all(len(d.encode()) <= 64 for _, d in row)


def test_card_marks_free_model():
    from reels_radar.cards import render_card
    row = {"theme": "Разное", "purposes": "note", "kind": "знание", "summary": "с", "template": "",
           "url": "u", "fail_reason": "free:router:m"}
    assert "бесплатной моделью" in render_card(row)
    row["fail_reason"] = None
    assert "бесплатной" not in render_card(row)

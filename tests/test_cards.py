from reels_radar.cards import render_card, keyboard_spec, parse_callback


def test_callback_roundtrip():
    for label, data in keyboard_spec("AAA")[0]:
        assert parse_callback(data)[1] == "AAA"


def test_card_has_no_long_dash(db):
    db.add_item("A", "https://i/reel/A/", "", 1)
    db.update("A", theme="ИИ", purposes="claude,note", kind="фича", summary="суть — вот", template="шаблон")
    text = render_card(db.get("A"))
    assert "—" not in text and "ИИ" in text and "суть" in text

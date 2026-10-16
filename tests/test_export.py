import json
from reels_radar.export import fix, shortcode, parse_export


def mojibake(s: str) -> str:
    return s.encode("utf8").decode("latin1")


def test_fix_roundtrip_and_plain():
    assert fix(mojibake("Описание")) == "Описание"
    assert fix("plain") == "plain"


def test_shortcode():
    assert shortcode("https://www.instagram.com/reel/AbC_1-x/?x=1") == "AbC_1-x"
    assert shortcode("https://example.com/") is None


def _saved(tmp_path, entries):
    (tmp_path / "saved_posts.json").write_text(json.dumps(entries))


def test_parse_saved_posts(tmp_path):
    _saved(tmp_path, [
        {"timestamp": 200, "media": [], "label_values": [
            {"label": "URL", "value": "https://www.instagram.com/reel/AAA/"},
            {"label": mojibake("Описание"), "value": mojibake("Как снимать")}]},
        {"timestamp": 100, "media": [], "label_values": [
            {"label": "URL", "value": "https://www.instagram.com/reel/BBB/"}]},
        {"timestamp": 50, "media": [], "label_values": [{"label": mojibake("Описание"), "value": "x"}]},
        {"timestamp": 10, "media": [], "label_values": [
            {"label": "URL", "value": "https://www.instagram.com/reel/AAA/"}]},
    ])
    items = parse_export(tmp_path)
    assert [i.code for i in items] == ["AAA", "BBB"]
    assert items[0].caption == "Как снимать" and items[1].caption == ""

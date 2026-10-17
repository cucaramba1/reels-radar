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


def test_parser_survives_odd_shapes(tmp_path):
    (tmp_path / "saved_posts.json").write_text(json.dumps({"saved_saved_media": [
        {"timestamp": None, "label_values": [{"label": "URL", "value": "https://www.instagram.com/reel/OK1/"}]},
        {"timestamp": 5, "label_values": [{"label": "URL", "value": 123}]},
        "garbage"]}))
    (tmp_path / "message_1.json").write_text("{not json")
    assert [i.code for i in parse_export(tmp_path)] == ["OK1"]


def test_url_is_rebuilt_from_code_no_argv_injection(tmp_path):
    (tmp_path / "saved_posts.json").write_text(json.dumps([
        {"timestamp": 1, "label_values": [{"label": "URL", "value": "--exec=evil instagram.com/reel/Ab_1/"}]}]))
    it = parse_export(tmp_path)[0]
    assert it.url == "https://www.instagram.com/reel/Ab_1/"


def test_owner_is_parsed_from_saved_posts(tmp_path):
    (tmp_path / "saved_posts.json").write_text(json.dumps([{"timestamp": 1, "label_values": [
        {"label": "URL", "value": "https://www.instagram.com/reel/OW1/"},
        {"dict": [{"dict": [{"label": mojibake("Имя пользователя"), "value": "some_author"}]}]}]}]))
    assert parse_export(tmp_path)[0].owner == "some_author"


def test_english_labels_caption_and_owner(tmp_path):
    (tmp_path / "saved_posts.json").write_text(json.dumps([{"timestamp": 1, "label_values": [
        {"label": "URL", "value": "https://www.instagram.com/reel/EN1/"},
        {"label": "Caption", "value": mojibake("Подпись рилса")},
        {"dict": [{"dict": [{"label": "Username", "value": "en_author"}]}]}]}]))
    it = parse_export(tmp_path)[0]
    assert it.caption == "Подпись рилса" and it.owner == "en_author"

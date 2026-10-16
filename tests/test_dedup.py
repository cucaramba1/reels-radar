import json
from reels_radar.dedup import known_codes, ingest
from reels_radar.export import Parsed


def test_known_codes_reads_all_sources(tmp_path, db):
    pipe, tools = tmp_path / "p", tmp_path / "t"
    pipe.mkdir(); tools.mkdir()
    (pipe / "items_by_key.json").write_text(json.dumps({"00001": {"url": "https://www.instagram.com/reel/OLD1/?x=1"}, "00002": {"url": "https://www.instagram.com/p/OLD2/"}, "00003": {}}))
    (tools / "results.jsonl").write_text(json.dumps({"code": "OLD3"}) + "\n" + "\n")
    db.add_item("DB1", "u", "", 1)
    assert known_codes(pipe, tools, db) == {"OLD1", "OLD2", "OLD3", "DB1"}


def test_missing_sources_ok(tmp_path, db):
    assert known_codes(tmp_path, tmp_path, db) == set()


def test_ingest_only_new(db):
    items = [Parsed("A", "u", "c", 1), Parsed("B", "u", "c", 2), Parsed("A", "u", "c", 3)]
    assert ingest(items, {"B"}, db) == 1
    assert db.get("A") is not None and db.get("B") is None

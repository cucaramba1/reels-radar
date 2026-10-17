import json
from pathlib import Path
from reels_radar.cli import main

PROJECT = Path(__file__).resolve().parent.parent


def test_ingest_counts_new(tmp_path, monkeypatch):
    exp = tmp_path / "exp"; exp.mkdir()
    (exp / "saved_posts.json").write_text(json.dumps([
        {"timestamp": 1, "media": [], "label_values": [{"label": "URL", "value": "https://www.instagram.com/reel/NEW1/"}]}]))
    monkeypatch.setenv("REELS_RADAR_ROOT", str(tmp_path))
    (tmp_path / "config").mkdir()
    for n in ("settings.yaml", "themes.yaml"):
        (tmp_path / "config" / n).write_text((PROJECT / "config" / n).read_text())
    assert main(["ingest", str(exp)]) == 0
    from reels_radar.db import DB
    assert DB(tmp_path / "data" / "radar.db").get("NEW1") is not None

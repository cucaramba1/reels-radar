import json
import re
from pathlib import Path
from reels_radar.cli import main

PROJECT = Path(__file__).resolve().parent.parent.parent


def test_sources_import_flag(tmp_path, monkeypatch, capsys):
    exp = tmp_path / "exp"; (exp / "connections").mkdir(parents=True)
    (exp / "connections" / "following.json").write_text(json.dumps({"relationships_following": [{"title": "old"}, {"title": "fresh"}]}))
    lp = tmp_path / "lp.jsonl"
    lp.write_text('{"u":"old","lastPost":"2019-01-01T00:00:00.000Z"}\n{"u":"fresh","lastPost":"2026-10-01T00:00:00.000Z"}\n')
    (tmp_path / "config").mkdir()
    cfg = (PROJECT / "config" / "settings.yaml").read_text()
    cfg = re.sub(r"last_posts_file: .*", f"last_posts_file: {lp}", cfg)
    cfg = re.sub(r"reels_pipeline: .*", f"reels_pipeline: {tmp_path}", cfg)
    (tmp_path / "config" / "settings.yaml").write_text(cfg)
    (tmp_path / "config" / "themes.yaml").write_text((PROJECT / "config" / "themes.yaml").read_text())
    monkeypatch.setenv("REELS_RADAR_ROOT", str(tmp_path))
    assert main(["sources", "import", "--export", str(exp)]) == 0
    assert main(["sources", "flag"]) == 0
    out = capsys.readouterr().out
    assert "подписок новых: 2" in out and "отложено на проверку: 1" in out
    from reels_radar.sources.db import SourcesDB
    sdb = SourcesDB(tmp_path / "data" / "sources.db")
    assert sdb.get("old")["needs_verify"] == 1 and sdb.get("old")["suggest_cleanup"] == 0
    assert sdb.get("fresh")["needs_verify"] == 0

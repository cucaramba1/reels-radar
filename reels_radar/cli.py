from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path

from .config import load_settings, load_themes
from .db import DB
from .dedup import ingest, known_codes
from .digest import build_digest
from .export import parse_export


def root() -> Path:
    return Path(os.environ.get("REELS_RADAR_ROOT") or Path(__file__).resolve().parent.parent)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reels-radar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest"); p.add_argument("export_dir")
    p = sub.add_parser("run"); p.add_argument("--limit", type=int)
    p = sub.add_parser("digest"); p.add_argument("--days", type=int, default=7)
    sub.add_parser("bot")
    a = ap.parse_args(argv)
    r = root()
    s, themes = load_settings(r), load_themes(r)
    db = DB(s.data_dir / "radar.db")
    if a.cmd == "ingest":
        n = ingest(parse_export(Path(a.export_dir)), known_codes(s.reels_pipeline, s.reels_tools, db), db)
        print(f"новых: {n}")
    elif a.cmd == "digest":
        print(build_digest(db, (datetime.now() - timedelta(days=a.days)).isoformat()))
    elif a.cmd == "run":
        from .live import run_live
        print(asyncio.run(run_live(s, db, themes, a.limit)))
    elif a.cmd == "bot":
        from .bot import run_bot
        asyncio.run(run_bot(s, db, themes))
    return 0

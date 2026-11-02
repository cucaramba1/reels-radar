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
from .slot import YIELDED


def root() -> Path:
    return Path(os.environ.get("REELS_RADAR_ROOT") or Path(__file__).resolve().parent.parent)


def _run_is_active() -> bool:
    """Идёт ли `reels_radar run` (pgrep на Windows нет, поэтому psutil)."""
    import psutil
    me = os.getpid()
    return any(p.pid != me and "reels_radar run" in " ".join(p.info["cmdline"] or ()).replace("-m reels_radar", "reels_radar")
               for p in psutil.process_iter(["cmdline"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reels-radar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest"); p.add_argument("export_dir")
    p = sub.add_parser("run"); p.add_argument("--limit", type=int)
    p = sub.add_parser("digest"); p.add_argument("--days", type=int, default=7); p.add_argument("--send", action="store_true")
    sub.add_parser("bot")
    sp = sub.add_parser("sources"); ssub = sp.add_subparsers(dest="scmd", required=True)
    pi = ssub.add_parser("import"); pi.add_argument("--export", required=True)
    for n in ("flag", "export", "stats"):
        ssub.add_parser(n)
    pv = ssub.add_parser("verify"); pv.add_argument("--limit", type=int, default=20)
    a = ap.parse_args(argv)
    r = root()
    s, themes = load_settings(r), load_themes(r)
    if a.cmd == "sources":
        from datetime import datetime as _dt
        from .sources.cleanup import export_cleanup, flag_for_verification
        from .sources.db import SourcesDB
        from .sources.importers import import_following, import_last_posts, import_saved_authors
        sdb = SourcesDB(s.data_dir / "sources.db")
        if a.scmd == "import":
            fol = next(Path(a.export).rglob("following.json"), None)
            print("подписок новых:", import_following(sdb, fol) if fol else 0)
            print("авторов сохранёнок новых:", import_saved_authors(
                sdb, s.reels_pipeline / "items_by_key.json", s.reels_pipeline / "final_theme_map.json", a.export))
            print("дат постов обновлено:", import_last_posts(sdb, s.last_posts_file) if s.last_posts_file.is_file() else 0)
        elif a.scmd == "flag":
            print("отложено на проверку:", flag_for_verification(sdb, _dt.now(), s.cleanup_years))
        elif a.scmd == "verify":
            from .sources.reader import ProfileReader
            from .sources.verify import budget_left, verify_batch
            if _run_is_active():
                print("идёт run_all: профили Instagram читать нельзя (один клиент), проверка не запущена")
                return 1
            left = min(a.limit, budget_left(sdb, s.verify_daily_budget, _dt.now()))
            if left <= 0:
                print("дневной бюджет проверок исчерпан")
                return 0
            reader = ProfileReader(s.data_dir / "pw-profile")
            try:
                res = verify_batch(sdb, reader, _dt.now(), s.cleanup_years, limit=left, pause=s.verify_pause)
                print(res)
            finally:
                reader.close()
            if res["stopped"] == "YIELD":
                return YIELDED
        elif a.scmd == "export":
            print("в списке на удаление:", export_cleanup(sdb, s.data_dir / "cleanup.txt"))
        else:
            print(sdb.counts())
        return 0
    db = DB(s.data_dir / "radar.db")
    if a.cmd == "ingest":
        n = ingest(parse_export(Path(a.export_dir)), known_codes(s.reels_pipeline, s.reels_tools, db), db)
        print(f"новых: {n}")
    elif a.cmd == "digest":
        import subprocess
        try:
            ver = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            ver = None
        text = build_digest(db, (datetime.now() - timedelta(days=a.days)).isoformat(), mark_repeat=a.send, ytdlp_version=ver)
        print(text)
        if a.send:
            async def _send():
                from aiogram import Bot
                bot = Bot(s.bot_token)
                try:
                    for i in range(0, len(text), 4000):
                        await bot.send_message(s.owner_id, text[i:i + 4000])
                finally:
                    await bot.session.close()
            asyncio.run(_send())
    elif a.cmd == "run":
        from .live import run_live
        res = asyncio.run(run_live(s, db, themes, a.limit))
        print(res)
        if res.get("yielded"):
            return YIELDED
    elif a.cmd == "bot":
        from .bot import run_bot
        asyncio.run(run_bot(s, db, themes))
    return 0

from __future__ import annotations

import shutil
from functools import partial
from pathlib import Path

from .fetch import fetch_chain, fetch_gallerydl, fetch_playwright, fetch_ytdlp
from .local import analyze_local
from .pipeline import run_batch
from .vision import classify


async def run_live(s, db, themes, limit=None):
    free = shutil.disk_usage(Path.home()).free / 1e9
    if free < s.min_free_gb:
        return {"error": "мало места на диске"}
    light = free < s.light_below_gb  # ночь не пропускаем: тяжёлое (видео + Whisper) откладываем, остальное разбираем
    cookies = s.reels_tools / "ig_cookies.txt"
    pw = (s.root / "scripts" / "pw_fetch.py", s.data_dir / "pw-profile")
    chain = [partial(fetch_ytdlp, cookies=cookies),
             lambda u, d: fetch_playwright(u, d, *pw),
             partial(fetch_gallerydl, cookies=cookies)]

    def fetch(row, work):
        return fetch_chain(row["url"], work, chain)

    def local(video, work, caption):
        return analyze_local(s, video, work, caption)

    class It:
        pass

    async def cls(row, lr):
        it = It(); it.code, it.caption = row["code"], row["caption"]
        return await classify(s, themes, it, lr, folder_theme=row["folder"], owner=row["owner"] or "")

    return await run_batch(s, db, themes, fetch=fetch, local=local, classify=cls, limit=limit, light=light)

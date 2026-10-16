from __future__ import annotations

import json
from pathlib import Path

from .db import DB
from .export import Parsed, shortcode


def _items_by_key(p: Path) -> set[str]:
    f = p / "items_by_key.json"
    if not f.exists():
        return set()
    d = json.load(open(f))
    vals = d.values() if isinstance(d, dict) else d
    return {c for v in vals if isinstance(v, dict) and (c := shortcode(v.get("url")))}


def _results(p: Path) -> set[str]:
    f = p / "results.jsonl"
    out = set()
    if f.exists():
        for line in open(f):
            line = line.strip()
            if line:
                try:
                    out.add(json.loads(line)["code"])
                except (ValueError, KeyError):
                    pass
    return out


def known_codes(reels_pipeline: Path, reels_tools: Path, db: DB) -> set[str]:
    known = _items_by_key(Path(reels_pipeline)) | _results(Path(reels_tools))
    known |= {r[0] for r in db.c.execute("SELECT code FROM items")}
    return known


def ingest(items: list[Parsed], known: set[str], db: DB) -> int:
    n = 0
    for it in items:
        if it.code in known:
            continue
        if db.add_item(it.code, it.url, it.caption, it.ts, it.folder):
            known.add(it.code)
            n += 1
    return n

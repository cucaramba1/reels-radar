from __future__ import annotations

import collections
import json
from pathlib import Path

from ..export import parse_export
from .db import SourcesDB, norm


def import_following(sdb: SourcesDB, path) -> int:
    data = json.load(open(path)).get("relationships_following", [])
    new = 0
    for x in data:
        u = norm(x.get("title") if isinstance(x, dict) else "")
        if not u:
            continue
        new += sdb.upsert(u, followed=1)
    return new


def import_saved_authors(sdb: SourcesDB, items_by_key_path, theme_map_path, export_dir) -> int:
    counts: collections.Counter = collections.Counter()
    themes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    ik = json.load(open(items_by_key_path)) if Path(items_by_key_path).exists() else {}
    tm = json.load(open(theme_map_path)) if Path(theme_map_path).exists() else {}
    for key, v in ik.items():
        a = norm(v.get("author") if isinstance(v, dict) else "")
        if a:
            counts[a] += 1
            if key in tm:
                themes[a][tm[key]] += 1
    for it in parse_export(Path(export_dir)):
        a = norm(it.owner)
        if a:
            counts[a] += 1
    new = 0
    for a, n in counts.items():
        fields = {"saved_count": n}
        if themes[a]:
            fields["themes"] = themes[a].most_common(1)[0][0]
        new += sdb.upsert(a, **fields)
        sdb.add_edge("me", a, "saved_author")
    return new


def import_last_posts(sdb: SourcesDB, jsonl_path) -> int:
    n = 0
    for line in open(jsonl_path):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        u = norm(r.get("u"))
        if not u:
            continue
        lp = r.get("lastPost")
        sdb.upsert(u, last_post_at=lp, posts_visible=1 if lp else 0)
        n += 1
    return n

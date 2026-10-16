from __future__ import annotations

import glob
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Parsed:
    code: str
    url: str
    caption: str
    ts: int
    folder: str | None = None


def fix(s) -> str:
    if not isinstance(s, str):
        return ""
    try:
        return s.encode("latin1").decode("utf8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def shortcode(url) -> str | None:
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else None


def _saved_posts(path) -> list[Parsed]:
    out = []
    for p in json.load(open(path)):
        url, cap = "", ""
        for lv in p.get("label_values", []):
            label = fix(lv.get("label", ""))
            if label == "URL":
                url = lv.get("value", "")
            elif label.startswith("Опис"):
                cap = fix(lv.get("value", ""))
        code = shortcode(url)
        if code:
            out.append(Parsed(code, url.split("?")[0], cap, int(p.get("timestamp", 0))))
    return out


def _messages(path) -> list[Parsed]:
    out = []
    for m in json.load(open(path)).get("messages", []):
        sh = m.get("share") or {}
        code = shortcode(sh.get("link"))
        if code:
            out.append(Parsed(code, sh["link"].split("?")[0], fix(sh.get("share_text")),
                              int(m.get("timestamp_ms", 0)) // 1000))
    return out


def parse_export(root: Path) -> list[Parsed]:
    found: dict[str, Parsed] = {}
    paths = [(p, _saved_posts) for p in glob.glob(str(Path(root) / "**" / "saved_posts.json"), recursive=True)]
    paths += [(p, _messages) for p in glob.glob(str(Path(root) / "**" / "message_*.json"), recursive=True)]
    for path, fn in paths:
        for it in fn(path):
            found.setdefault(it.code, it)
    return sorted(found.values(), key=lambda x: -x.ts)

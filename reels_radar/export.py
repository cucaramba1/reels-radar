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
    owner: str = ""


def fix(s) -> str:
    if not isinstance(s, str):
        return ""
    try:
        return s.encode("latin1").decode("utf8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def shortcode(url) -> str | None:
    if not isinstance(url, str):
        return None
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def canonical(code: str) -> str:
    return f"https://www.instagram.com/reel/{code}/"


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _saved_posts(path) -> list[Parsed]:
    out = []
    data = json.load(open(path))
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), [])
    for p in data:
        if not isinstance(p, dict):
            continue
        url, cap, owner = "", "", ""
        for lv in p.get("label_values", []):
            if not isinstance(lv, dict):
                continue
            for d in lv.get("dict") or []:
                for dd in (d.get("dict") or []) if isinstance(d, dict) else []:
                    if isinstance(dd, dict) and fix(dd.get("label", "")) in ("Имя пользователя", "Username"):
                        owner = str(dd.get("value") or "")
            label = fix(lv.get("label", ""))
            if label == "URL":
                url = lv.get("value", "")
            elif label.startswith("Опис") or label == "Caption":
                cap = fix(lv.get("value", ""))
        code = shortcode(url)
        if code:
            out.append(Parsed(code, canonical(code), cap, _int(p.get("timestamp")), None, owner))
    return out


def _messages(path) -> list[Parsed]:
    out = []
    for m in json.load(open(path)).get("messages", []):
        sh = m.get("share") if isinstance(m, dict) else None
        sh = sh if isinstance(sh, dict) else {}
        code = shortcode(sh.get("link"))
        if code:
            out.append(Parsed(code, canonical(code), fix(sh.get("share_text")),
                              _int(m.get("timestamp_ms")) // 1000))
    return out


def parse_export(root: Path) -> list[Parsed]:
    found: dict[str, Parsed] = {}
    paths = [(p, _saved_posts) for p in glob.glob(str(Path(root) / "**" / "saved_posts.json"), recursive=True)]
    paths += [(p, _messages) for p in glob.glob(str(Path(root) / "**" / "message_*.json"), recursive=True)]
    for path, fn in paths:
        try:
            items = fn(path)
        except (OSError, ValueError, AttributeError):
            continue
        for it in items:
            found.setdefault(it.code, it)
    return sorted(found.values(), key=lambda x: -x.ts)

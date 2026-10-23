from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .activity import CHANNELS, Activity

TIMELINE_KEY = "xdt_api__v1__feed__user_timeline_graphql_connection"
POSTS = {"feed", "carousel_container"}


@dataclass(frozen=True)
class Node:
    taken_at: int
    product_type: str
    collab: bool


def parse_timeline(responses) -> list[Node]:
    """Узлы ленты из ответов api/graphql; чужие ключи и узлы без даты игнорируются."""
    out = []
    for r in responses:
        try:
            edges = (r.get("data", {}).get(TIMELINE_KEY) or {}).get("edges") or []
        except AttributeError:
            continue
        for e in edges:
            n = (e or {}).get("node") or {}
            if not n.get("taken_at"):
                continue
            out.append(Node(int(n["taken_at"]), n.get("product_type") or "", bool(n.get("coauthor_producers"))))
    return out


def _num(s: str) -> int:
    s = s.replace(",", "").upper()
    mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(s[-1], 1)
    return int(float(s[:-1] if mult > 1 else s) * mult)


def parse_meta(text: str | None) -> tuple[int | None, int | None, int | None]:
    """(followers, following, posts) из og:description: «198K Followers, 4,057 Following, 2,895 Posts»."""
    def g(word):
        m = re.search(r"([\d.,]+[KMB]?)\s+" + word, text or "", re.I)
        return _num(m.group(1)) if m else None
    return g("Followers"), g("Following"), g("Posts")


def classify_page(text: str) -> str:
    if re.search(r"This account is private|аккаунт закрыт|закрытый аккаунт", text, re.I):
        return "private"
    if re.search(r"isn't available|недоступна|Sorry, this page", text, re.I):
        return "not_found"
    return "ok"


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _max(nodes) -> str | None:
    return _iso(max(n.taken_at for n in nodes)) if nodes else None


def build_activity(nodes: list[Node], posts_count: int | None, ring: bool, status: str) -> Activity:
    if status == "not_found":
        return Activity(error="NOT_FOUND")
    if status == "private":
        return Activity(private=True, posts_count=posts_count)
    if not nodes and posts_count != 0:
        return Activity(error="NO_TIMELINE", posts_count=posts_count, story_active=ring)
    return Activity(
        last_post=_max([n for n in nodes if n.product_type in POSTS and not n.collab]),
        last_reel=_max([n for n in nodes if n.product_type == "clips"]),
        last_collab=_max([n for n in nodes if n.collab]),
        story_active=ring, posts_count=posts_count, channels=frozenset(CHANNELS))

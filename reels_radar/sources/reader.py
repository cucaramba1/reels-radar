"""Тонкий слой Playwright: читает 4 канала активности профиля Instagram. Без юнит-тестов (сеть).

Правило: один клиент, один постоянный профиль data/pw-profile, только чтение.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .activity import Activity
from .profile_parse import TIMELINE_KEY, build_activity, classify_page, parse_meta, parse_timeline

RING_JS = """() => {
  const img = document.querySelector('header img[alt*="profile picture"], header img[alt*="фото профиля"]');
  const wrap = img && img.closest('[role="button"]');
  return !!(wrap && wrap.querySelector('canvas'));
}"""


class ProfileReader:
    def __init__(self, profile_dir: Path, wait_s: float = 12.0):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.ctx = self._pw.chromium.launch_persistent_context(
            str(profile_dir), headless=True, viewport={"width": 1280, "height": 1400})
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.wait_ms = int(wait_s * 1000)

    def close(self) -> None:
        self.ctx.close()
        self._pw.stop()

    def __call__(self, username: str) -> Activity:
        page, resps = self.page, []

        def on(r):
            try:
                if "graphql" in r.url and r.request.resource_type in ("xhr", "fetch"):
                    t = r.text()
                    if TIMELINE_KEY in t:
                        resps.append(json.loads(t))
            except Exception:
                pass

        page.on("response", on)
        try:
            resp = page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=30000)
            code = resp.status if resp else None
            if code in (429, 403):
                return Activity(error="RATE")
            waited = 0
            while not resps and waited < self.wait_ms and "/accounts/login" not in page.url:
                page.wait_for_timeout(500)
                waited += 500
            if re.search(r"/accounts/login|/challenge|/suspended", page.url):
                return Activity(error="LOGIN")
            page.wait_for_timeout(1500)  # шапка и кольцо историй дорисовываются позже ленты
            body = page.inner_text("body")[:3000]
            m = page.query_selector('meta[property="og:description"]')
            posts = parse_meta(m.get_attribute("content") if m else None)[2]
            return build_activity(parse_timeline(resps), posts, page.evaluate(RING_JS), classify_page(body))
        except Exception as e:
            return Activity(error="READ_" + type(e).__name__)
        finally:
            page.remove_listener("response", on)

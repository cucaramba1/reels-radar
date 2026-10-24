"""pw_fetch.py URL DEST PROFILE: открыть рилс в залогиненном профиле и перехватить URL медиа.
Коды выхода: 0 готово, 2 нужен логин, 3 лимит, 1 не вышло. Не печатает cookie."""
import sys, urllib.request
from pathlib import Path
from playwright.sync_api import TimeoutError as PwTimeout, sync_playwright

url, dest, profile = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
media = []
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(profile, headless=True)
    page = ctx.new_page()
    page.on("response", lambda r: media.append(r.url) if "video" in r.headers.get("content-type", "") else None)
    try:
        page.goto(url, wait_until="networkidle", timeout=60000)
    except PwTimeout:
        pass  # у Instagram сеть часто не затихает, а медиа к этому времени уже перехвачено
    if "/accounts/login" in page.url:
        sys.exit(2)
    page.wait_for_timeout(3000)
    ctx.close()
if not media:
    sys.exit(1)
src = media[-1].split("&bytestart")[0]
req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
(dest / "pw.mp4").write_bytes(urllib.request.urlopen(req, timeout=120).read())
sys.exit(0)

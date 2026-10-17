"""ig_login.py: открыть окно браузера, человек входит в Instagram сам (пароль и 2FA вводит он),
затем сохранить сессию в tools/reels/ig_state.json и обновить ig_cookies.txt. Пароль не читается и не хранится."""
import shutil, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "data" / "pw-profile"
STATE = Path.home() / "Claude Code/tools/reels/ig_state.json"
deadline = time.time() + 15 * 60
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=False, viewport={"width": 1100, "height": 900})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
    page.bring_to_front()
    subprocess.run(["osascript", "-e", 'tell application "Chromium" to activate'], capture_output=True)
    print("ждём вход...", flush=True)
    ok = False
    while time.time() < deadline:
        names = {c["name"] for c in ctx.cookies("https://www.instagram.com")}
        if "sessionid" in names:
            time.sleep(4)  # дать странице дописать cookie после входа
            ok = True
            break
        time.sleep(3)
    if ok:
        if STATE.exists():
            shutil.copy2(STATE, STATE.with_suffix(".json.bak"))
        ctx.storage_state(path=str(STATE))
        STATE.chmod(0o600)
        print("сессия сохранена", flush=True)
    ctx.close()
if ok:
    r = subprocess.run([sys.executable, str(STATE.parent / "refresh_cookies.py")], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip()[-200:])
else:
    print("время вышло, вход не выполнен")

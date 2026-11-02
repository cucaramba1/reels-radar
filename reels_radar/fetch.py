from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Callable

VID = {".mp4", ".mov", ".webm"}
IMG = {".jpg", ".jpeg", ".png", ".webp"}
Fetcher = Callable[[str, Path], str]


def _video(dest: Path) -> Path | None:
    return next((p for p in sorted(Path(dest).glob("*")) if p.suffix.lower() in VID), None)


def has_video_stream(p: Path) -> bool:
    """Playwright иногда перехватывает аудиодорожку DASH под видом .mp4: без кадров это не рилс."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=index",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True, timeout=60)
    return bool(r.stdout.strip())


def images(dest: Path) -> list[Path]:
    return [p for p in sorted(Path(dest).glob("*")) if p.suffix.lower() in IMG]


def _classify(err: str) -> str | None:
    e = err.lower()
    if "login_required" in e or "redirect to login" in e or "log in" in e:
        return "LOGIN"
    if "429" in e or "rate limit" in e or "please wait a few minutes" in e or "redirect to home page" in e:
        return "RATE"
    return None


def fetch_ytdlp(url: str, dest: Path, cookies: Path) -> str:
    p = subprocess.run(["yt-dlp", "--cookies", str(cookies), "-o", str(dest / "%(id)s.%(ext)s"), url],
                       capture_output=True, text=True, timeout=300)
    return "OK" if p.returncode == 0 else (_classify(p.stderr + p.stdout) or "NO_VIDEO")


def fetch_gallerydl(url: str, dest: Path, cookies: Path) -> str:
    p = subprocess.run(["gallery-dl", "--cookies", str(cookies), "-D", str(dest), url],
                       capture_output=True, text=True, timeout=300)
    return "OK" if p.returncode == 0 else (_classify(p.stderr + p.stdout) or "NO_VIDEO")


def _kill_tree(p: subprocess.Popen) -> None:
    if sys.platform == "win32":  # killpg нет: taskkill /T гасит и дерево (node-драйвер с Chromium)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    else:
        os.killpg(p.pid, signal.SIGKILL)


def fetch_playwright(url: str, dest: Path, script: Path, profile: Path) -> str:
    # своя группа процессов: по таймауту гасим и node-драйвер с Chromium, иначе они живут и держат профиль
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32"
             else {"start_new_session": True})
    p = subprocess.Popen([sys.executable, str(script), url, str(dest), str(profile)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **group)
    try:
        code = p.wait(timeout=300)
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        p.wait()
        return "NO_VIDEO"
    return {0: "OK", 2: "LOGIN", 3: "RATE"}.get(code, "NO_VIDEO")


def fetch_chain(url: str, dest: Path, fetchers: list[Fetcher]) -> tuple[str, Path | None]:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    last = "NO_VIDEO"
    for f in fetchers:
        st = f(url, dest)
        if st == "RATE":
            return "RATE", None
        if st == "OK":
            v = _video(dest)
            if v and not has_video_stream(v):
                v.unlink()  # только звук: пробуем следующий загрузчик (фотопост отдаст картинки)
                v = None
            if v:
                return "OK", v
            if images(dest):
                return "OK", dest  # карусель из фото: дальше OCR слайдов, без расшифровки речи
            st = "NO_VIDEO"
        last = st
    return ("LOGIN" if last == "LOGIN" else "NO_VIDEO"), None

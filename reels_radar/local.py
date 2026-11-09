from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


@dataclass
class LocalResult:
    transcript: str
    ocr_text: str
    score: float
    frames: list[Path]


def clean_lines(blocks: list[str]) -> list[str]:
    seen, out = set(), []
    for blk in blocks:
        for ln in blk.splitlines():
            ln = ln.strip()
            key = re.sub(r"[^\wа-яё]+", "", ln.lower())
            if len(key) < 3 or re.fullmatch(r"[\d:.,]+", ln) or key in seen:
                continue
            seen.add(key)
            out.append(ln)
    return out


def score(transcript: str, ocr_text: str, caption: str, keywords: list[str]) -> float:
    s = min(len(transcript) / 20, 50) + min(len(ocr_text) / 20, 25)
    hay = f"{transcript} {ocr_text} {caption}".lower()
    s += min(sum(1 for k in keywords if k in hay) * 5, 25)
    return round(min(s, 100.0), 1)


def extract_frames(video: Path, out: Path, n: int) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    raw = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, timeout=60).stdout.strip()
    try:
        dur = float(raw)
    except ValueError:
        dur = 0.0
    step = max(dur / (n + 1), 0.5)
    for i in range(n):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(step * (i + 1)), "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=720:-1", str(out / f"f{i:02d}.jpg")], timeout=60)
    return sorted(out.glob("f*.jpg"))


SHOT_MAX, SHOT_MIN_SEC, NO_SPEECH_CHARS = 10, 0.8, 200


def _duration(video: Path) -> float:
    raw = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def shot_times(cuts: list[float], dur: float, n_max: int = SHOT_MAX) -> list[float]:
    """Моменты для кадров: по одному на план, на 45% его длины; планы короче 0.8 с вливаются в соседний.
    Края ролика (по 8%) не берём: там заставки и логотипы. Приём из kurbaitaev/saved-to-notes (shots.py, acquire.py)."""
    lo, hi = dur * 0.08, dur * 0.92
    bounds = [lo] + [c for c in sorted(cuts) if lo < c < hi] + [hi]
    shots: list[list[float]] = []
    for a, b in zip(bounds, bounds[1:]):
        if shots and b - a < SHOT_MIN_SEC:
            shots[-1][1] = b
        else:
            shots.append([a, b])
    times = [a + (b - a) * 0.45 for a, b in shots if b - a > 0]
    if len(times) > n_max:  # слишком много планов: равномерно прореживаем
        times = [times[round(i * (len(times) - 1) / (n_max - 1))] for i in range(n_max)]
    return times


def scene_cuts(video: Path, threshold: float = 0.2) -> list[float]:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-an", "-vf", f"select='gt(scene,{threshold})',showinfo",
                        "-f", "null", "-"], capture_output=True, text=True, timeout=300)
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", p.stderr)]


def frames_at(video: Path, out: Path, times: list[float]) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(times):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=720:-2", "-q:v", "4", str(out / f"f{i:02d}.jpg")], timeout=60)
    return sorted(out.glob("f*.jpg"))


def run_ocr(ocr_bin: Path, paths: list[Path]) -> list[str]:
    if not paths:
        return []
    r = subprocess.run([str(ocr_bin), *map(str, paths)], capture_output=True, text=True, timeout=600)
    return [b.strip() for b in r.stdout.split("=====")]


def has_audio(video: Path) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True, timeout=60)
    return bool(r.stdout.strip())


def transcribe(whisper_bin: str, model: str, video: Path, tmp: Path) -> str:
    if not has_audio(video):
        return ""  # беззвучный ролик: речи нет, это не сбой
    tmp.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([whisper_bin, str(video), "--model", model, "--output-format", "json",
                        "--output-dir", str(tmp), "--verbose", "False", "--condition-on-previous-text", "False"],
                       capture_output=True, text=True, timeout=900)
    f = tmp / (video.stem + ".json")
    if p.returncode != 0 or not f.exists():
        raise RuntimeError(f"whisper failed: {(p.stderr or '')[-200:]}")
    return _finish(json.loads(f.read_text() or "{}"))


def _finish(res: dict) -> str:
    """Ответ распознавания (Whisper локально или Groq) -> текст; музыка и дежурные фразы дают пустую строку."""
    if is_hallucination(res.get("segments") or []):
        return ""  # музыка без слов: Whisper уверенно выдумывает текст, такой транскрипт хуже пустого
    text = (res.get("text") or "").strip()
    if _STOCK.sub("", text).strip(" .,!?…-") == "":
        return ""  # только дежурные фразы, которые Whisper пишет на музыке и тишине
    return text if len(text) >= 15 else ""


# Типовые галлюцинации Whisper (выучены на субтитрах YouTube): на музыке он пишет их уверенно,
# no_speech_prob при этом бывает 0.0 (живая проверка 25.10: синус 440 Гц дал «Thank you.»)
_STOCK = re.compile(r"(?i)(субтитры (сделал|создавал|подготовил)\w*[^.!?\n]*|редактор субтитров[^.!?\n]*|"
                    r"продолжение следует|спасибо за (просмотр|внимание)|подписывайтесь на (канал|наш канал)|"
                    r"thank you( for watching)?|thanks for watching|please subscribe|you)[.!?…]*")


def is_hallucination(segments: list[dict]) -> bool:
    """По клипу целиком (приём из kurbaitaev/saved-to-notes): половина сегментов похожа на тишину
    (no_speech_prob > 0.5) и при этом модель не уверена в словах (avg_logprob < -0.5)."""
    bad = sum(1 for g in segments if g.get("no_speech_prob", 0) > 0.5 and g.get("avg_logprob", 0) < -0.5)
    return bool(segments) and bad * 2 >= len(segments)


def _groq_request(audio: Path, key: str, tries: int = 4) -> dict:
    """Groq whisper-large-v3-turbo через urllib (multipart руками, без новых зависимостей). 429: ждём retry-after."""
    boundary = uuid.uuid4().hex
    fields = {"model": "whisper-large-v3-turbo", "response_format": "verbose_json", "temperature": "0"}
    body = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items())
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{audio.name}"\r\n'
             f'Content-Type: audio/mpeg\r\n\r\n').encode() + audio.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    for i in range(tries):
        rq = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", body, {
            "Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "reels-radar/1.0"})
        try:
            with urllib.request.urlopen(rq, timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(min(float(e.headers.get("retry-after") or 20), 90))
                continue
            raise RuntimeError(f"groq {e.code}: {e.read().decode(errors='ignore')[:200]}")
    raise RuntimeError("groq: попытки кончились")


def transcribe_groq(video: Path, tmp: Path) -> str:
    """Сервер: Mac-овского mlx_whisper нет, речь расшифровывает Groq. Ролики короткие, один запрос без нарезки."""
    if not has_audio(video):
        return ""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY не задан")
    tmp.mkdir(parents=True, exist_ok=True)
    mp3 = tmp / (video.stem + ".mp3")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
                    "-b:a", "48k", str(mp3)], check=True, timeout=300)
    if mp3.stat().st_size > 24 * 1024 * 1024:
        raise RuntimeError("аудио больше 24 МБ, нужна нарезка")
    return _finish(_groq_request(mp3, key))


def analyze_local(s: Settings, video: Path, workdir: Path, caption: str = "") -> LocalResult:
    video = Path(video)
    if video.is_dir():  # карусель: слайды вместо кадров, речи нет
        from .fetch import images
        frames = images(video)[: s.max_frames]
        transcript = ""
    else:
        transcript = (transcribe_groq(video, workdir / "stt") if os.environ.get("STT") == "groq"
                      else transcribe(s.whisper_bin, s.whisper_model, video, workdir / "stt"))
        frames = []
        if len(transcript) < NO_SPEECH_CHARS:  # без речи весь смысл в кадрах: кадр на каждый план, а не 6 через равные промежутки
            times = shot_times(scene_cuts(video), _duration(video))
            frames = frames_at(video, workdir / "frames", times) if len(times) > s.max_frames else []
        frames = frames or extract_frames(video, workdir / "frames", s.max_frames)
    ocr_text = " / ".join(clean_lines(run_ocr(s.ocr_bin or s.reels_tools / "ocr", frames)))
    return LocalResult(transcript, ocr_text, score(transcript, ocr_text, caption, s.keywords), frames)

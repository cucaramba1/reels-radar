from __future__ import annotations

import json
import re
import subprocess
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
    res = json.loads(f.read_text() or "{}")
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


def analyze_local(s: Settings, video: Path, workdir: Path, caption: str = "") -> LocalResult:
    video = Path(video)
    if video.is_dir():  # карусель: слайды вместо кадров, речи нет
        from .fetch import images
        frames = images(video)[: s.max_frames]
        transcript = ""
    else:
        frames = extract_frames(video, workdir / "frames", s.max_frames)
        transcript = transcribe(s.whisper_bin, s.whisper_model, video, workdir / "stt")
    ocr_text = " / ".join(clean_lines(run_ocr(s.reels_tools / "ocr", frames)))
    return LocalResult(transcript, ocr_text, score(transcript, ocr_text, caption, s.keywords), frames)

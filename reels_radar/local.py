from __future__ import annotations

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


def transcribe(whisper_bin: str, model: str, video: Path, tmp: Path) -> str:
    tmp.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([whisper_bin, str(video), "--model", model, "--output-format", "txt",
                        "--output-dir", str(tmp), "--verbose", "False", "--condition-on-previous-text", "False"],
                       capture_output=True, text=True, timeout=900)
    f = tmp / (video.stem + ".txt")
    if p.returncode != 0 or not f.exists():
        raise RuntimeError(f"whisper failed: {(p.stderr or '')[-200:]}")
    text = f.read_text().strip()
    return text if len(text) >= 15 else ""


def analyze_local(s: Settings, video: Path, workdir: Path, caption: str = "") -> LocalResult:
    frames = extract_frames(video, workdir / "frames", s.max_frames)
    ocr_text = " / ".join(clean_lines(run_ocr(s.reels_tools / "ocr", frames)))
    transcript = transcribe(s.whisper_bin, s.whisper_model, video, workdir / "stt")
    return LocalResult(transcript, ocr_text, score(transcript, ocr_text, caption, s.keywords), frames)

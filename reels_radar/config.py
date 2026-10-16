from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class Theme:
    name: str
    folder: str | None
    moc: str | None


@dataclass
class Settings:
    root: Path
    data_dir: Path
    vault: Path
    bot_token: str
    owner_id: int
    reels_tools: Path
    reels_pipeline: Path
    claude_bin: str
    whisper_bin: str
    whisper_model: str
    select_threshold: float
    max_frames: int
    batch_size: int
    min_free_gb: float
    claude_timeout: int
    keywords: list[str]


def load_settings(root: Path) -> Settings:
    load_dotenv(root / ".env")
    y = yaml.safe_load((root / "config" / "settings.yaml").read_text())
    return Settings(
        root=root,
        data_dir=root / y["data_dir"],
        vault=Path(os.environ.get("VAULT", "")),
        bot_token=os.environ.get("BOT_TOKEN", ""),
        owner_id=int(os.environ.get("OWNER_ID") or 0),
        reels_tools=Path(y["reels_tools"]),
        reels_pipeline=Path(y["reels_pipeline"]),
        claude_bin=y["claude_bin"],
        whisper_bin=y["whisper_bin"],
        whisper_model=y["whisper_model"],
        select_threshold=float(y["select_threshold"]),
        max_frames=int(y["max_frames"]),
        batch_size=int(y["batch_size"]),
        min_free_gb=float(y["min_free_gb"]),
        claude_timeout=int(y["claude_timeout"]),
        keywords=[k.lower() for k in y["keywords"]],
    )


def load_themes(root: Path) -> dict[str, Theme]:
    y = yaml.safe_load((root / "config" / "themes.yaml").read_text())
    return {n: Theme(n, v.get("folder"), v.get("moc")) for n, v in y["themes"].items()}

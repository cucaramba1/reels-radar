from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


def _p(v: str) -> str:
    """~ и $VAR в путях из конфига: один settings.yaml работает на разных машинах и учётках."""
    return os.path.expanduser(os.path.expandvars(str(v)))


@dataclass(frozen=True)
class Theme:
    name: str
    folder: str | None
    moc: str | None
    vault: str | None = None   # корень другого vault (Досуг); None = основной
    canvas: str | None = None  # путь холста относительно корня; по умолчанию <folder>.canvas


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
    last_posts_file: Path
    cleanup_years: int
    verify_daily_budget: int = 60
    light_below_gb: float = 10.0  # меньше свободно: «лёгкая ночь», видео ждут, карусели идут
    verify_pause: tuple = (6.0, 10.0)
    ocr_bin: Path | None = None  # исполняемый файл OCR: пути кадров аргументами, блоки текста через "=====" в stdout; None = <reels_tools>/ocr


def load_settings(root: Path) -> Settings:
    load_dotenv(root / ".env")
    y = yaml.safe_load((root / "config" / "settings.yaml").read_text())
    return Settings(
        root=root,
        data_dir=root / y["data_dir"],
        vault=Path(os.environ.get("VAULT", "")),
        bot_token=os.environ.get("BOT_TOKEN", ""),
        owner_id=int(os.environ.get("OWNER_ID") or 0),
        reels_tools=Path(_p(y["reels_tools"])),
        reels_pipeline=Path(_p(y["reels_pipeline"])),
        claude_bin=_p(os.environ.get("CLAUDE_BIN") or y["claude_bin"]),
        whisper_bin=_p(os.environ.get("WHISPER_BIN") or y["whisper_bin"]),
        whisper_model=os.environ.get("WHISPER_MODEL") or y["whisper_model"],
        select_threshold=float(y["select_threshold"]),
        max_frames=int(y["max_frames"]),
        batch_size=int(y["batch_size"]),
        min_free_gb=float(y["min_free_gb"]),
        claude_timeout=int(y["claude_timeout"]),
        keywords=[k.lower() for k in y["keywords"]],
        last_posts_file=Path(_p(y.get("last_posts_file", ""))),
        cleanup_years=int(y.get("cleanup_years", 2)),
        light_below_gb=float(y.get("light_below_gb", 10)),
        verify_daily_budget=int(y.get("verify_daily_budget", 60)),
        verify_pause=tuple(float(x) for x in y.get("verify_pause", [6, 10])),
        ocr_bin=Path(_p(os.environ.get("OCR_BIN") or y["ocr_bin"])) if (os.environ.get("OCR_BIN") or y.get("ocr_bin")) else None,
    )


def load_vaults(root: Path) -> dict[str, str]:
    """Дополнительные vault'ы по ключам из themes.yaml. VAULT_<КЛЮЧ> в окружении подменяет путь (сервер: зеркало vault)."""
    y = yaml.safe_load((root / "config" / "themes.yaml").read_text())
    return {k: os.environ.get(f"VAULT_{k.upper()}") or _p(v) for k, v in (y.get("vaults") or {}).items()}


def load_themes(root: Path) -> dict[str, Theme]:
    y = yaml.safe_load((root / "config" / "themes.yaml").read_text())
    vaults = load_vaults(root)
    return {n: Theme(n, v.get("folder"), v.get("moc"), vaults.get(v.get("vault")), v.get("canvas"))
            for n, v in y["themes"].items()}

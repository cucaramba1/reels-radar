from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import Theme


def safe_title(title: str) -> str:
    t = re.sub(r'[\\/:*?"<>|]', "", title)
    return re.sub(r"\s+", " ", t).strip()[:80] or "Без названия"


def write_note(vault: Path, theme: Theme, title: str, body: str, code: str) -> tuple[Path, bool]:
    folder = Path(vault) / theme.folder
    folder.mkdir(parents=True, exist_ok=True)
    base = safe_title(title)
    path, n = folder / f"{base}.md", 2
    while path.exists():
        path = folder / f"{base} ({n}).md"
        n += 1
    assert path.resolve().is_relative_to(folder.resolve())
    path.write_text(body.rstrip() + "\n", encoding="utf8")
    return path, True


def add_moc_line(vault: Path, theme: Theme, title: str) -> str:
    moc = Path(vault) / theme.folder / theme.moc
    line = f"- [[{safe_title(title)}]]"
    text = moc.read_text(encoding="utf8") if moc.exists() else ""
    if line not in text:
        moc.parent.mkdir(parents=True, exist_ok=True)
        moc.write_text(text.rstrip("\n") + "\n" + line + "\n", encoding="utf8")
    return line


def rollback(vault: Path, db, code: str, themes: dict[str, Theme]) -> str:
    r = db.get(code)
    if not r or not r["note_path"]:
        return "нечего откатывать"
    src = Path(vault) / r["note_path"]
    if src.exists():
        dst = Path(vault) / ".trash" / r["note_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    theme = themes.get(r["theme"])
    if theme and r["moc_line"]:
        moc = Path(vault) / theme.folder / theme.moc
        if moc.exists():
            moc.write_text(moc.read_text(encoding="utf8").replace(r["moc_line"] + "\n", ""), encoding="utf8")
    db.update(code, status="draft", note_path=None, note_created=None, moc_line=None)
    return "заметка перенесена в .trash"

from __future__ import annotations

import json
import re
import shutil
import uuid
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
    moc = (theme.moc or "")[:-3] if (theme.moc or "").endswith(".md") else (theme.moc or "")
    text = f"# {title.strip()}\n\n{body.strip()}\n\n## Связанные заметки\n- [[{moc}]]\n"
    path.write_text(text, encoding="utf8")
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


def add_to_canvas(vault: Path, theme: Theme, note_rel: str) -> bool:
    """Файловая нода заметки на холст раздела + стрелка от MOC. Нет холста: ничего не делаем."""
    cv = Path(vault) / f"{theme.folder}.canvas"
    if not cv.exists():
        return False
    data = json.loads(cv.read_text(encoding="utf8"))
    nodes = data.setdefault("nodes", [])
    if any(n.get("file") == note_rel for n in nodes):
        return True
    x = min((n.get("x", 0) for n in nodes), default=0)
    y = max((n.get("y", 0) + n.get("height", 0) for n in nodes), default=0) + 40
    node = {"id": uuid.uuid4().hex[:16], "type": "file", "file": note_rel, "x": x, "y": y,
            "width": 400, "height": 200}
    nodes.append(node)
    moc = next((n for n in nodes if str(n.get("file", "")).endswith(theme.moc or "\0")), None)
    if moc:
        data.setdefault("edges", []).append(
            {"id": uuid.uuid4().hex[:16], "fromNode": moc["id"], "fromSide": "bottom",
             "toNode": node["id"], "toSide": "top"})
    cv.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")
    return True

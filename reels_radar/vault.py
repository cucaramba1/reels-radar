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
    root = Path(r["note_vault"] or vault)
    src = root / r["note_path"]
    if src.exists():
        dst = root / ".trash" / r["note_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    theme = themes.get(r["theme"])
    moc_rel = r["moc_rel"] or (f"{theme.folder}/{theme.moc}" if theme and theme.folder and theme.moc else None)
    if moc_rel and r["moc_line"]:
        moc = root / moc_rel
        if moc.exists():
            moc.write_text(moc.read_text(encoding="utf8").replace(r["moc_line"] + "\n", ""), encoding="utf8")
    cv_rel = r["canvas_rel"] or (canvas_rel(theme) if theme and theme.folder else None)
    cv = root / cv_rel if cv_rel else None
    if cv and cv.exists():
        data = json.loads(cv.read_text(encoding="utf8"))
        gone = {n["id"] for n in data.get("nodes", []) if n.get("file") == r["note_path"]}
        if gone:
            data["nodes"] = [n for n in data["nodes"] if n["id"] not in gone]
            data["edges"] = [e for e in data.get("edges", []) if e.get("fromNode") not in gone and e.get("toNode") not in gone]
            cv.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")
    db.update(code, status="draft", note_path=None, note_created=None, moc_line=None, decision=None,
              note_vault=None, moc_rel=None, canvas_rel=None)
    return "заметка перенесена в .trash"


def canvas_rel(theme) -> str:
    return getattr(theme, "canvas", None) or f"{theme.folder}.canvas"


def root_of(theme, vault: Path) -> Path:
    return Path(getattr(theme, "vault", None) or vault)


def add_to_canvas(vault: Path, theme: Theme, note_rel: str) -> bool:
    """Файловая нода заметки на холст раздела + стрелка от MOC. Нет холста: ничего не делаем."""
    cv = Path(vault) / canvas_rel(theme)
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


def _stem(name: str) -> str:
    return name[:-3] if name.endswith(".md") else name


def ensure_section(root: Path, sec, parent=None, intro: str = "") -> bool:
    """Папка + MOC + холст раздела (идемпотентно). С parent: вход вверх и строка в его MOC/холсте. True, если создавали."""
    root = Path(root)
    folder = root / sec.folder
    moc = folder / sec.moc
    created = False
    if not moc.exists():
        folder.mkdir(parents=True, exist_ok=True)
        text = f"# {sec.name}\n\n" + (intro.strip() + "\n\n" if intro.strip() else "") + "## Заметки\n"
        if parent is not None:
            text += f"\n## Связанные заметки\n- [[{_stem(parent.moc)}]]\n"
        moc.write_text(text, encoding="utf8")
        created = True
    cv = root / canvas_rel(sec)
    if not cv.exists():
        moc_rel = f"{sec.folder}/{sec.moc}"
        nodes = [{"id": uuid.uuid4().hex[:16], "type": "file", "file": moc_rel, "x": 0, "y": 0, "width": 400, "height": 200}]
        cv.write_text(json.dumps({"nodes": nodes, "edges": []}, ensure_ascii=False, indent=2), encoding="utf8")
        created = True
    if created and parent is not None:
        pmoc = root / parent.folder / parent.moc
        if pmoc.exists():
            t = pmoc.read_text(encoding="utf8")
            line = f"- [[{_stem(sec.moc)}]]"
            if line not in t:
                if "## Подразделы" not in t:
                    t = t.rstrip("\n") + "\n\n## Подразделы\n"
                pmoc.write_text(t.rstrip("\n") + "\n" + line + "\n", encoding="utf8")
        add_to_canvas(root, parent, f"{sec.folder}/{sec.moc}")
    return created


def catalog(vault: Path, themes: dict[str, Theme]) -> list[Theme]:
    """Все разделы с холстом: из themes.yaml плюс найденные в корнях vault'ов (холст + папка + MOC)."""
    roots = {Path(vault)} | {Path(t.vault) for t in themes.values() if t.vault}
    out, seen = [], set()
    for t in themes.values():
        if t.folder and t.moc and (root_of(t, vault), t.folder) not in seen:
            out.append(t)
            seen.add((root_of(t, vault), t.folder))
    for root in roots:
        for cv in sorted(root.glob("*.canvas")):
            name = cv.stem
            if (root, name) in seen or not (root / name / f"{name} — карта заметок.md").exists():
                continue
            out.append(Theme(name, name, f"{name} — карта заметок.md", None if root == Path(vault) else str(root)))
            seen.add((root, name))
    return sorted(out, key=lambda t: t.folder)

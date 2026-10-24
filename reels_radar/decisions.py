"""Решения по карточке (flow v2): заметка / идея для рилса / вдохновение / отклонить, и откат решения."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from .config import Theme
from .vault import add_moc_line, add_to_canvas, canvas_rel, catalog, ensure_section, root_of, rollback, safe_title, write_note

CONTENT = Theme("Съёмка и монтаж", "Контент и соцсети", "Контент и соцсети — карта заметок.md")
IDEAS = Theme("Идеи для рилсов", "Контент и соцсети/Идеи для рилсов", "Идеи для рилсов — карта заметок.md",
              None, "Идеи для рилсов.canvas")
INSPO_ROOT = Theme("Вдохновение", "Контент и соцсети/Вдохновение", "Вдохновение — карта заметок.md",
                   None, "Вдохновение.canvas")
INSPO = {
    "visual": Theme("Вдохновение: визуал", "Контент и соцсети/Вдохновение/Визуал", "Вдохновение — визуал — карта заметок.md",
                    None, "Вдохновение — визуал.canvas"),
    "memes": Theme("Вдохновение: мемы", "Контент и соцсети/Вдохновение/Мемы", "Вдохновение — мемы — карта заметок.md",
                   None, "Вдохновение — мемы.canvas"),
    "ideas": Theme("Вдохновение: идеи", "Контент и соцсети/Вдохновение/Идеи", "Вдохновение — идеи — карта заметок.md",
                   None, "Вдохновение — идеи.canvas"),
}
log = logging.getLogger(__name__)
INSPO_LABEL = {"visual": "визуал", "memes": "мемы", "ideas": "идеи"}


def sec_hash(sec: Theme) -> str:
    return hashlib.md5(sec.folder.encode()).hexdigest()[:6]


def find_section(sections: list[Theme], h: str) -> Theme | None:
    return next((t for t in sections if sec_hash(t) == h), None)


def proposed(sections: list[Theme], r) -> Theme | None:
    """Раздел, который предложил claude (по теме карточки), если он уже есть с папкой и холстом."""
    return next((t for t in sections if t.name == r["theme"] and t.folder), None)


def _publish(db, code, sec: Theme, vault: Path, title: str, body: str, decision: str, parent=None) -> str:
    root = root_of(sec, vault)
    if parent is not None:
        ensure_section(root, sec, parent)
    path, created = write_note(root, sec, title, body, code)
    # статус сразу после заметки: если MOC или холст упадут, повторное нажатие не создаст «(2)», а ↩️ найдёт заметку
    db.update(code, status="written", note_path=str(path.relative_to(root)), note_created=int(created),
              note_vault=str(root), moc_rel=f"{sec.folder}/{sec.moc}", canvas_rel=canvas_rel(sec), decision=decision)
    db.update(code, moc_line=add_moc_line(root, sec, path.stem))
    try:
        add_to_canvas(root, sec, str(path.relative_to(root)))
    except (ValueError, OSError) as e:  # холст битый или Obsidian пишет его прямо сейчас
        log.warning("холст %s не обновлён: %s", canvas_rel(sec), e)
        return f"записано: {path.name} (на холст не добавлено, холст не читается)"
    return f"записано: {path.name}"


def _ready(db, code) -> bool:
    return db.get(code)["status"] == "draft"


def write_note_to(db, code, sec: Theme, vault: Path, intro: str = "") -> str:
    """Заметка в выбранный раздел; раздела ещё нет (предложение темы или «новый холст») - создаём."""
    if not _ready(db, code):
        return "уже обработано"
    r = db.get(code)
    ensure_section(root_of(sec, vault), sec, None, intro)
    return _publish(db, code, sec, vault, r["title"], r["body"], f"note:{sec.folder}")


def write_idea(db, code, vault: Path) -> str:
    if not _ready(db, code):
        return "уже обработано"
    r = db.get(code)
    body = f"{(r['summary'] or '').strip()}\n\n## Структура рилса\n{(r['template'] or 'структура не задана').strip()}"
    return _publish(db, code, IDEAS, vault, r["title"], body, "idea", parent=CONTENT)


def write_inspiration(db, code, kind: str, vault: Path) -> str:
    if not _ready(db, code):
        return "уже обработано"
    r = db.get(code)
    root = Path(vault)
    ensure_section(root, INSPO_ROOT, CONTENT)
    ensure_section(root, INSPO[kind], INSPO_ROOT)
    body = f"{(r['summary'] or '').strip()}\n\n{(r['body'] or '').strip()}".strip()
    return _publish(db, code, INSPO[kind], vault, r["title"], body, f"inspo:{kind}")


def reject(db, code, why: str = "reject") -> str:
    if not _ready(db, code):
        return "уже обработано"
    db.update(code, status="rejected", decision=why)
    return "отклонено"


def undo(db, code, vault: Path, themes) -> str:
    r = db.get(code)
    if r["status"] == "draft":
        return "уже черновик"
    if r["note_path"]:
        rollback(vault, db, code, themes)
    else:
        db.update(code, status="draft", decision=None)
    return "возвращено"


DECISION_LABEL = {"idea": "🎬 идея для рилса", "friend": "👥 друзьям (отклонено)", "reject": "❌ отклонено"}


def decision_label(r) -> str:
    d = r["decision"] or ""
    if d.startswith("note:"):
        return "📝 заметка → " + d[5:]
    if d.startswith("inspo:"):
        return "✨ вдохновение: " + INSPO_LABEL.get(d[6:], d[6:])
    return DECISION_LABEL.get(d, d or r["status"])


def new_section(name: str, vault: str | None = None) -> Theme:
    n = safe_title(name)
    return Theme(n, n, f"{n} — карта заметок.md", vault)

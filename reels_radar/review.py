from __future__ import annotations

from pathlib import Path

from .vault import add_moc_line, write_note

WRITES = {"note", "product", "claude"}


def save_verdict(db, code, v) -> None:
    db.update(code, status="archived" if v.skip else "draft", fail_reason=v.reason or None,
              theme=v.theme, purposes=",".join(v.purposes), kind=v.kind, summary=v.summary,
              template=v.template, title=v.title, body=v.body)


def apply_action(db, code, action, themes, vault: Path) -> str:
    r = db.get(code)
    if action == "no":
        db.update(code, status="rejected")
        return "отклонено"
    if action.startswith("set_theme:"):
        name = action.split(":", 1)[1]
        if name in themes:
            db.update(code, theme=name)
        return f"тема: {name}"
    if action.startswith("set_purposes:"):
        db.update(code, purposes=action.split(":", 1)[1])
        return "цели обновлены"
    if action == "ok":
        purposes = set((r["purposes"] or "").split(","))
        if not purposes & WRITES:
            db.update(code, status="approved")
            return "сохранено в базе"
        theme = themes[r["theme"]]
        path, created = write_note(vault, theme, r["title"], r["body"], code)
        line = add_moc_line(vault, theme, r["title"])
        db.update(code, status="written", note_path=str(path.relative_to(vault)),
                  note_created=int(created), moc_line=line)
        return f"записано: {path.name}"
    raise ValueError(f"unknown action {action}")

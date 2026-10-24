from __future__ import annotations

HELP = """Кнопки карточки:
📝 заметка (потом выбираешь холст: предложенный, другой или новый)
🎬 идея для рилса (покажу структуру, можно принять или поправить текстом)
✨ вдохновение (🎨 визуал, 😂 мемы, 💡 идея)
👥 друзьям (пока то же, что отклонить)
❌ отклонить
После решения остаются ℹ️ (что выбрано) и ↩️ (вернуть карточку обратно, заметка откатится).
/find монтаж звук: поиск по всем разобранным рилсам (название, суть, речь, текст на экране)."""


def render_card(row, show_template: bool = False) -> str:
    parts = [f"{row['theme']} | {row['purposes']} | {row['kind']}", "", row["summary"] or ""]
    try:
        if (row["fail_reason"] or "").startswith("free:"):
            parts[1:1] = ["⚠ Разобрано бесплатной моделью без кадров, тему выбери сам"]
    except (KeyError, IndexError):
        pass
    if show_template and row["template"]:
        parts += ["", "Структура рилса:", row["template"]]
    body = "\n".join(parts).replace("—", "-")
    if len(body) > 3900:  # лимит Telegram 4096, ссылка должна остаться
        body = body[:3900].rstrip() + "…"
    return body + "\n\n" + row["url"]


def keyboard_spec(code: str) -> list[list[tuple[str, str]]]:
    return [[("📝", f"n:{code}"), ("🎬", f"i:{code}"), ("✨", f"s:{code}"), ("👥", f"f:{code}"), ("❌", f"x:{code}")]]


def note_menu(code: str, proposed_label: str | None, can_create: str | None) -> list[list[tuple[str, str]]]:
    first = []
    if proposed_label:
        first.append((f"✅ {proposed_label}", f"nk:{code}"))
    elif can_create:
        first.append((f"➕ создать «{can_create}»", f"nc:{code}"))
    return [first, [("🗂 Другой холст", f"nl:{code}"), ("➕ Новый холст", f"nn:{code}")], [("⬅️", f"b:{code}")]] if first else \
        [[("🗂 Другой холст", f"nl:{code}"), ("➕ Новый холст", f"nn:{code}")], [("⬅️", f"b:{code}")]]


def idea_menu(code: str) -> list[list[tuple[str, str]]]:
    return [[("✅", f"ik:{code}"), ("✏️", f"ie:{code}"), ("⬅️", f"b:{code}")]]


def inspo_menu(code: str) -> list[list[tuple[str, str]]]:
    return [[("🎨", f"sv:{code}"), ("😂", f"sm:{code}"), ("💡", f"si:{code}")], [("⬅️", f"b:{code}")]]


def done_menu(label: str, code: str) -> list[list[tuple[str, str]]]:
    return [[(f"ℹ️ {label}"[:60], f"info:{code}"), ("↩️ Вернуть", f"u:{code}")]]


def parse_callback(data: str) -> tuple[str, str]:
    action, code = data.split(":", 1)
    return action, code


def section_cb(h: str, code: str) -> str:
    return f"ns:{h}:{code}"

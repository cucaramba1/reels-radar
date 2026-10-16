from __future__ import annotations

from dataclasses import dataclass

from .claude import run_claude
from .config import Theme

PURPOSES = ("note", "content", "product", "claude", "friend")
KINDS = ("знание", "приём", "идея", "фича")

SYSTEM = """Ты разбираешь сохранённый рилс Некита для его Obsidian и контента. Отвечай по-русски, строго по JSON-схеме.
Оценивай по кадрам (файлы изображений можно открыть инструментом Read) и расшифровке, не только по подписи.
purposes, можно несколько: note (знание или приём в заметку), content (идея и шаблон для его рилсов и тредов), product (идея фичи продукта), claude (улучшение работы Claude: скилл, фича, промпт, сетап), friend (переслать другу, в заметки не пишется).
Тема строго из списка. title: содержательное название заметки до 80 символов, без авторов и каналов. body: суть markdown без заголовка верхнего уровня, промпты и команды дословно в блоке кода.
Для content заполни template: хук, структура по секундам, длительность, звук, что снимать. Для темы «Слова и фразы» body = фраза, смысл, где уместна.
skip=true с reason, если рилс пустой, реклама, воронка без сути. Не выдумывай то, чего нет в материале. Без длинного тире, имён авторов и юзернеймов."""

SCHEMA = {
    "type": "object",
    "properties": {
        "theme": {"type": "string"}, "purposes": {"type": "array", "items": {"type": "string"}},
        "kind": {"type": "string"}, "summary": {"type": "string"}, "template": {"type": "string"},
        "title": {"type": "string"}, "body": {"type": "string"}, "skip": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["theme", "purposes", "kind", "summary", "template", "title", "body", "skip", "reason"],
}


@dataclass
class Verdict:
    theme: str
    purposes: list[str]
    kind: str
    summary: str
    template: str
    title: str
    body: str
    skip: bool = False
    reason: str = ""


def _clean(s: str) -> str:
    return (s or "").replace("—", "-").strip()


def validate(raw: dict, themes: dict[str, Theme]) -> Verdict:
    theme = raw.get("theme") if raw.get("theme") in themes else "Разное"
    purposes = [p for p in raw.get("purposes", []) if p in PURPOSES] or ["note"]
    kind = raw.get("kind") if raw.get("kind") in KINDS else "знание"
    return Verdict(theme, purposes, kind, _clean(raw.get("summary")), _clean(raw.get("template")),
                   _clean(raw.get("title"))[:80], _clean(raw.get("body")), bool(raw.get("skip")),
                   _clean(raw.get("reason")))


def build_prompt(code, caption, transcript, ocr_text, frames, themes, folder_theme) -> str:
    parts = [f"Темы: {', '.join(themes)}."]
    if folder_theme:
        parts.append(f"Папка Instagram задаёт тему: {folder_theme}.")
    parts += [f"Подпись: {caption}", f"Расшифровка речи: {transcript}", f"Текст на экране (OCR): {ocr_text}"]
    if frames:
        parts.append("Кадры (открой через Read): " + ", ".join(str(f) for f in frames))
    return "\n".join(parts)


async def classify(s, themes, item, local, claude=run_claude, folder_theme=None) -> Verdict:
    prompt = build_prompt(item.code, item.caption, local.transcript, local.ocr_text, local.frames,
                          themes, folder_theme)
    dirs = tuple({str(f.parent) for f in local.frames})
    raw = await claude(s, prompt, system=SYSTEM, schema=SCHEMA, tools=("Read",) if local.frames else (),
                       add_dirs=dirs, timeout=s.claude_timeout)
    return validate(raw, themes)

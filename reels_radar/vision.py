from __future__ import annotations

import re
from dataclasses import dataclass

from .claude import llm_fallback, run_claude_free
from .config import Theme

PURPOSES = ("note", "content", "product", "claude", "friend")
KINDS = ("знание", "приём", "идея", "фича")

SYSTEM = """Ты разбираешь сохранённый рилс Некита для его Obsidian и контента. Отвечай по-русски, строго по JSON-схеме.
Оценивай по кадрам (файлы изображений можно открыть инструментом Read) и расшифровке, не только по подписи.
purposes, можно несколько: note (знание или приём в заметку), content (идея и шаблон для его рилсов и тредов), product (идея фичи продукта), claude (улучшение работы Claude: скилл, фича, промпт, сетап), friend (переслать другу, в заметки не пишется).
Тема строго из списка. title: содержательное название заметки до 80 символов, без авторов и каналов. body: суть markdown без заголовка верхнего уровня, промпты и команды дословно в блоке кода.
Для content заполни template: хук, структура по секундам, длительность, звук, что снимать. Для темы «Слова и фразы» body = фраза, смысл, где уместна.
Некит сохраняет рилсы осознанно, значит ценное есть в самом видео. Если рилс выглядит как реклама или воронка («напиши слово в комментарии, пришлю ссылку»), призыв и воронку игнорируй, а вытащи то, что реально показано и сказано: приёмы, настройки, шаги, инструменты, идею. Если по материалу видно только обещание, а содержания нет, не скипай: сделай карточку, начни summary со слов «Только обещание:» и опиши, что обещано и что видно в кадрах.
skip=true (с reason) только если в рилсе вообще нечего взять ни по кадрам, ни по речи. Не выдумывай то, чего нет в материале. Без длинного тире, имён авторов и юзернеймов."""

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


HANDLE = re.compile(r"@[\w.]+")


def _scrub(s: str, owner: str = "") -> str:
    s = HANDLE.sub("", s or "")
    if owner:
        s = re.sub(re.escape(owner), "автор", s, flags=re.I)
    return s


def _clean(s: str, owner: str = "") -> str:
    return _scrub(s, owner).replace("—", "-").strip()


def validate(raw: dict, themes: dict[str, Theme], owner: str = "") -> Verdict:
    theme = raw.get("theme") if raw.get("theme") in themes else "Разное"
    purposes = [p for p in raw.get("purposes", []) if p in PURPOSES] or ["note"]
    kind = raw.get("kind") if raw.get("kind") in KINDS else "знание"
    c = lambda k: _clean(raw.get(k), owner)  # noqa: E731
    return Verdict(theme, purposes, kind, c("summary"), c("template"), c("title")[:80], c("body"),
                   bool(raw.get("skip")), c("reason"))


def build_prompt(code, caption, transcript, ocr_text, frames, themes, folder_theme) -> str:
    parts = [f"Темы: {', '.join(themes)}."]
    if folder_theme:
        parts.append(f"Папка Instagram задаёт тему: {folder_theme}.")
    parts += [f"Подпись: {caption}", f"Расшифровка речи: {transcript}", f"Текст на экране (OCR): {ocr_text}"]
    if frames:
        parts.append("Кадры (открой через Read): " + ", ".join(str(f) for f in frames))
    return "\n".join(parts)


async def classify(s, themes, item, local, claude=run_claude_free, folder_theme=None, owner="") -> Verdict:
    prompt = build_prompt(item.code, item.caption, local.transcript, local.ocr_text, local.frames,
                          themes, folder_theme)
    dirs = tuple({str(f.parent) for f in local.frames})
    raw = await claude(s, prompt, system=SYSTEM, schema=SCHEMA, tools=("Read",) if local.frames else (),
                       add_dirs=dirs, timeout=s.claude_timeout)
    v = validate(raw, themes, owner)
    if claude is run_claude_free and llm_fallback.last_backend.startswith("router"):
        # запас без кадров: тему не доверяем (в тесте замера 61% совпадений), Некит выберет кнопкой 🏷
        v.theme = folder_theme if folder_theme in themes else "Разное"
        if not v.skip:
            v.reason = "free:" + llm_fallback.last_backend
    return v

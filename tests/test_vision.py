import asyncio
from reels_radar.config import Theme
from reels_radar.vision import validate, build_prompt, classify

THEMES = {"ИИ": Theme("ИИ", "f", "m"), "Разное": Theme("Разное", "f", "m")}


def test_validate_normalizes():
    v = validate({"theme": "Нет такой", "purposes": [], "kind": "знание", "summary": "а — б",
                  "template": "", "title": "Заголовок: тест/1", "body": "текст", "skip": False,
                  "reason": ""}, THEMES)
    assert v.theme == "Разное" and v.purposes == ["note"] and "—" not in v.summary


def test_validate_drops_unknown_purposes():
    v = validate({"theme": "ИИ", "purposes": ["claude", "bogus"], "kind": "приём", "summary": "s",
                  "template": "", "title": "t", "body": "b", "skip": False, "reason": ""}, THEMES)
    assert v.purposes == ["claude"]


def test_prompt_has_no_author_and_lists_themes():
    p = build_prompt("C", "подпись", "расшифровка", "ocr", [], THEMES, None)
    assert "ИИ" in p and "расшифровка" in p and "@" not in p


def test_classify_uses_claude_and_validates():
    async def fake(s, prompt, **kw):
        return {"theme": "ИИ", "purposes": ["claude", "note"], "kind": "фича", "summary": "суть",
                "template": "", "title": "Заголовок", "body": "тело", "skip": False, "reason": ""}
    class S:
        claude_timeout = 5
    class Item: code, caption = "C", "c"
    class Local: transcript, ocr_text, frames = "т", "о", []
    v = asyncio.run(classify(S(), THEMES, Item(), Local(), claude=fake))
    assert v.theme == "ИИ" and v.purposes == ["claude", "note"]

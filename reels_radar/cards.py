from __future__ import annotations


def render_card(row) -> str:
    parts = [f"{row['theme']} | {row['purposes']} | {row['kind']}", "", row["summary"] or ""]
    if row["template"]:
        parts += ["", "Шаблон:", row["template"]]
    parts += ["", row["url"]]
    return "\n".join(parts).replace("—", "-")


def keyboard_spec(code: str) -> list[list[tuple[str, str]]]:
    return [[("✅", f"ok:{code}"), ("❌", f"no:{code}"), ("✏️", f"edit:{code}"), ("🏷", f"theme:{code}")]]


def parse_callback(data: str) -> tuple[str, str]:
    action, code = data.split(":", 1)
    return action, code

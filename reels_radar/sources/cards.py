from __future__ import annotations


def account_text(row) -> str:
    parts = [f"@{row['username']}", row["why"] or "", f"https://www.instagram.com/{row['username']}/"]
    return "\n".join(p for p in parts if p).replace("—", "-")


def account_keyboard(username: str) -> list[list[tuple[str, str]]]:
    return [[("🗑 на удаление", f"ac:del:{username}"), ("✅ оставить", f"ac:keep:{username}"),
             ("👤 личный", f"ac:personal:{username}")]]


def parse_account_cb(data: str) -> tuple[str, str]:
    _, action, username = data.split(":", 2)
    return action, username


def chunk_lines(lines: list[str], limit: int = 3500) -> list[str]:
    out, cur = [], ""
    for ln in lines:
        add = ln if not cur else "\n" + ln
        if cur and len(cur) + len(add) > limit:
            out.append(cur)
            cur = ln
        else:
            cur += add
    if cur:
        out.append(cur)
    return out

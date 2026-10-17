from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

CHANNELS = ("posts", "reels", "collab", "stories")


@dataclass
class Activity:
    last_post: str | None = None
    last_reel: str | None = None
    last_collab: str | None = None
    story_active: bool = False
    private: bool = False
    channels: frozenset = frozenset()
    error: str | None = None


def activity_last(a: Activity) -> str | None:
    dates = [d for d in (a.last_post, a.last_reel, a.last_collab) if d]
    return max(dates) if dates else None


def decide(a: Activity, now: datetime, years: int) -> tuple[str, str]:
    if a.error:
        return "unknown", f"ошибка чтения: {a.error}"
    if a.private:
        return "unknown", "закрытый профиль, активность не проверить"
    cutoff = now.replace(year=now.year - years).strftime("%Y-%m-%d")
    last = activity_last(a)
    if a.story_active or (last and last[:10] >= cutoff):
        return "active", f"активен: последний сигнал {last[:10] if last else 'истории'}"
    if set(CHANNELS) <= set(a.channels):
        why = (f"нет активности с {cutoff}: пост {(a.last_post or 'нет')[:10]}, рилс {(a.last_reel or 'нет')[:10]}, "
               f"коллаб {(a.last_collab or 'нет')[:10]}, историй нет")
        return "inactive", why
    if a.channels:
        return "unknown", "проверены не все каналы: " + ", ".join(sorted(a.channels))
    return "unknown", "проверка не выполнена"

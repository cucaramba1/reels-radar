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
    posts_count: int | None = None


def activity_last(a: Activity) -> str | None:
    dates = [d for d in (a.last_post, a.last_reel, a.last_collab) if d]
    return max(dates) if dates else None


def _day(d: str) -> str | None:
    """YYYY-MM-DD из ISO-строки или None, если формат непонятен."""
    try:
        return datetime.fromisoformat(d.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def _cutoff(now: datetime, years: int) -> str:
    try:
        return now.replace(year=now.year - years).strftime("%Y-%m-%d")
    except ValueError:  # 29 февраля
        return now.replace(year=now.year - years, day=28).strftime("%Y-%m-%d")


def decide(a: Activity, now: datetime, years: int) -> tuple[str, str]:
    if a.error:
        return "unknown", f"ошибка чтения: {a.error}"
    if a.private:
        return "unknown", "закрытый профиль, активность не проверить"
    cutoff = _cutoff(now, years)
    days = [(d, _day(d)) for d in (a.last_post, a.last_reel, a.last_collab) if d]
    if any(day is None for _, day in days):
        return "unknown", "непонятный формат даты, активность не определена"
    last = max((day for _, day in days), default=None)
    if a.story_active or (last and last >= cutoff):
        return "active", f"активен: последний сигнал {last or 'истории'}"
    if not days and a.posts_count != 0:
        return "unknown", "дат нет и пустой профиль не подтверждён (возможно, не загрузилось)"
    if set(CHANNELS) <= set(a.channels):
        why = (f"нет активности с {cutoff}: пост {(a.last_post or 'нет')[:10]}, рилс {(a.last_reel or 'нет')[:10]}, "
               f"коллаб {(a.last_collab or 'нет')[:10]}, историй нет")
        return "inactive", why
    if a.channels:
        return "unknown", "проверены не все каналы: " + ", ".join(sorted(a.channels))
    return "unknown", "проверка не выполнена"

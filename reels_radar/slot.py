from __future__ import annotations

import os
from pathlib import Path

YIELDED = 75  # код выхода «уступил слот, не доделал»: tools/slot не засчитывает прогон и перезапустит позже


def should_yield() -> bool:
    """Флаг tools/slot: пора доделать текущий элемент и выйти (Некит работает или мало памяти)."""
    return Path(os.environ.get("SLOT_YIELD", Path.home() / "Claude Code/tools/slot/state/yield")).exists()

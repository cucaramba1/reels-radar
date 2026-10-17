#!/bin/zsh
# Прогон очереди пачками по 30 до конца или до паузы (лимит claude / RATE / LOGIN). Лог: data/runall.log
cd "$(dirname "$0")/.." || exit 1
while true; do
  echo "=== $(date '+%F %T') batch" >> data/runall.log
  uv run python -m reels_radar run --limit 30 >> data/runall.log 2>&1
  left=$(uv run python -c "from pathlib import Path; from reels_radar.db import DB; d=DB(Path('data/radar.db')); print(d.counts().get('new',0), d.kv_get('paused','0'))")
  echo "left/paused: $left" >> data/runall.log
  read -r n_left paused <<< "$left"   # zsh не делит $left на слова сам
  [ "$n_left" -eq 0 ] && break
  [ "$paused" = "1" ] && break
done
echo "=== done $(date '+%F %T')" >> data/runall.log

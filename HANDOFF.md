# HANDOFF: Reels Radar

Обновлено: 2026-10-16. Спека: docs/superpowers/specs/2026-10-16-reels-radar-core-design.md. План: docs/superpowers/plans/2026-10-16-reels-radar-core.md. Ветка `feat/core`, 51 тест зелёный, в master не влито.

## Сделано
Задачи 1-10 плана + фикс-проход по финальному ревью. Бот @cucaramba_reels_radar_bot создан, токен в .env (600). Рилс про Ootto скачан и расшифрован через yt-dlp (cookies tools/reels/ig_cookies.txt живые).

## Осталось (Task 11, живой пилот, с Некитом)
1. Темы vs vault: нет папок для Психология (близко «Продуктивность и привычки»), Фитнес, Юмор, Путешествия, Кулинария, Слова и фразы, Разное. Решить сопоставление, поправить config/themes.yaml, создать «Слова и фразы» с MOC и холстом.
2. Playwright: `uv add playwright && uv run playwright install chromium`, логин Некита в data/pw-profile, проверка scripts/pw_fetch.py. Профиль Playwright MCP «nhatrang» занят другой сессией, не трогать.
3. Новый экспорт Instagram от Некита: `uv run python -m reels_radar ingest <папка>`, проверить файл коллекций (папки), при наличии добавить разбор folder в export.py с тестом.
4. Пилот: `run --limit 5` (включая сетап про автоматизацию Instagram), калибровка select_threshold, расход лимита claude.
5. Хендлер F.video: Некит шлёт видео боту, подпись `/file <code>`, бот расшифровывает, no_video возвращается в поток. Без него no_video тупик (не писан, нужен живой бот).
6. launchd: ночной run, воскресный digest. Плисты по образцу ~/Claude Code/schedules/launchd, ставит Некит руками.
7. Почта <почта> подключена (mcp__mail, аккаунт mailru) для автовыгрузки IG (подпроект C, спайк не начат).

## Deferred minors
✏️ ничего не делает; is_limit по подстроке слишком широкий; в названии заметки не вырезаются [ ] # ^; message_*.json берёт рилсы от других людей; фильтра авторов в коде нет, только в промпте.

## Подпроекты
B: Threads (искать самому, логин не проблема), Reddit, TG-каналы. C: автоэкспорт IG через браузер + письмо на <почта>.

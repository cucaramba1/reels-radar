# План S1b: читатель профиля Instagram

Основание: docs/superpowers/specs/2026-10-17-s1-spike-report.md, раздел «Дизайн читателя профиля».

## Критерии готовности
- `uv run pytest -q` зелёный (105 + новые).
- Чистые функции покрыты тестами без сети: parse_timeline, parse_meta, build_activity.
- ProfileReader не запускается в тестах; живой прогон только после конца run_all и с ведома Некита.
- `sources verify` вызывает verify_batch с реальным читателем, дневной бюджет в конфиге (старт 60).

## Шаги
1. `reels_radar/sources/profile_parse.py` (чистый код, TDD):
   - parse_timeline(json) -> list[Node(taken_at, product_type, collab)] по ключу xdt_api__v1__feed__user_timeline_graphql_connection.
   - parse_meta(text) -> (followers, following, posts) из og:description, «198K», «4,057».
   - classify_page(text) -> private / not_found / ok.
   - build_activity(nodes, posts_count, ring, private, not_found) -> Activity: максимум дат (закрепы), коллаб отдельно, channels = все 4 только если лента получена или posts_count == 0.
2. Конфиг: `verify_daily_budget: 60`, `verify_pause: [6, 10]`; счётчик дневного бюджета по таблице checks.
3. `reels_radar/sources/reader.py` ProfileReader (Playwright, тонкий слой, без юнит-тестов): профиль data/pw-profile, headless, ожидание ленты до 12 с, стоп на редиректе на вход / 429 / 403 / challenge (error=LOGIN/RATE/CHALLENGE), NOT_FOUND = benign.
4. Подключить в cli.py `sources verify` (проверка pgrep run_all, бюджет, итоги).
5. Живой прогон: 3 профиля (mikhnesss, money, ne.gor.e.gor), сохранить фикстуры, затем очередь 630 пачками. Только после run_all, с Некитом.

## Что делегируем бесплатным моделям
Нечего: чистая логика с тестами, делаю сам (риск ошибки в правилах «неактивен» выше выгоды).

# Sources S2: реестр аккаунтов и чистка подписок Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Отдельная БД аккаунтов `data/sources.db`: импорт подписок, авторов сохранёнок и дат последних постов, предложения на чистку, бот-ревью `/cleanup` и список на ручную отписку.

**Architecture:** Новый модуль `reels_radar/sources/` с `SourcesDB` (stdlib sqlite3), чистыми функциями импорта, правил чистки и действий над аккаунтом; бот получает 3 команды и callback `ac:`. Запросов к Instagram нет совсем: всё из файлов на диске.

**Tech Stack:** Python 3.12, sqlite3, aiogram (уже в проекте), pytest.

**Spec:** `docs/superpowers/specs/2026-10-17-sources-registry-design.md` (этап S2). S1 (спайк) и S3-S5 в других планах.

## Global Constraints

- Бот и код **ничего не отписывают и не нажимают** в Instagram: только чтение файлов и запись в `sources.db` (решение Некита, спека «Чистка»).
- Аккаунт со статусом `personal` никогда не попадает в предложения на чистку.
- Аккаунт, у которого есть сохранёнки (`saved_count > 0`), не предлагается на чистку.
- Юзернеймы нормализуются в нижний регистр без `@`.
- Без длинного тире (—) в текстах бота и файле списка.
- Callback data ≤ 64 байта: `ac:<action>:<username>`, юзернейм Instagram не длиннее 30 символов.
- Тесты только на `tmp_path`, в живой `data/` и vault не пишут.
- Коммиты с трейлером `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Ветка `feat/sources`.

## Review Focus

- Запись в списках с пустым или `null` юзернеймом, дубли с разным регистром: не падает, одна запись (Task 2).
- Повторный импорт: счётчики и ручные пометки Некита (`reviewed`, `intent`, `status`) не затираются (Task 2).
- Аккаунт без видимых постов, но с сохранёнками или помеченный `personal`: не предлагается (Task 3).
- Двойной клик на 🗑 или смена решения: итоговое состояние одно и предсказуемо (Task 4).
- Юзернейм с точкой, подчёркиванием, цифрами в callback data разбирается правильно (Task 4).

---

## File Structure

```
reels_radar/sources/__init__.py
reels_radar/sources/db.py        SourcesDB
reels_radar/sources/importers.py import_following, import_saved_authors, import_last_posts
reels_radar/sources/cleanup.py   suggest_cleanup, candidates, apply_action, export_cleanup
reels_radar/sources/cards.py     account_text, account_keyboard, parse_account_cb
reels_radar/bot.py               +/cleanup, /cleanup_list, /done, callback ac:
reels_radar/cli.py               +sources import|suggest|export
config/settings.yaml             +last_posts_file, cleanup_years
tests/sources/test_*.py
```

---

### Task 1: SourcesDB

**Files:** Create `reels_radar/sources/__init__.py`, `reels_radar/sources/db.py`; Test `tests/sources/__init__.py`, `tests/sources/conftest.py`, `tests/sources/test_db.py`

**Interfaces:**
- Produces: `SourcesDB(path)` with `upsert(username, **fields) -> bool` (True если создан), `get(username) -> Row | None`, `update(username, **fields)`, `by_status(status, limit=1000) -> list[Row]`, `counts() -> dict[str,int]`, `add_edge(parent, child, kind)`, `log_check(username, result)`. Поля: `status, intent, themes, priority, value_score, posts_per_week, last_post_at, posts_visible, followers, bio, why, suggest_cleanup, reviewed, followed, saved_count, depth, notes, first_seen, last_checked, next_check`. `norm(username) -> str`.

- [ ] **Step 1: Failing test** `tests/sources/test_db.py`:
```python
from reels_radar.sources.db import norm


def test_norm():
    assert norm("@Some.User ") == "some.user"
    assert norm(None) == ""


def test_upsert_creates_then_updates(sdb):
    assert sdb.upsert("@Bob", followed=1) is True
    assert sdb.upsert("bob", themes="ИИ") is False
    r = sdb.get("BOB")
    assert r["followed"] == 1 and r["themes"] == "ИИ" and r["status"] == "candidate" and r["intent"] == "none"


def test_empty_username_ignored(sdb):
    assert sdb.upsert("", followed=1) is False
    assert sdb.upsert(None, followed=1) is False
    assert sdb.counts() == {}


def test_unknown_field_rejected(sdb):
    import pytest
    with pytest.raises(KeyError):
        sdb.upsert("a", bogus=1)


def test_edges_and_checks(sdb):
    sdb.upsert("a"); sdb.upsert("b")
    sdb.add_edge("a", "b", "similar"); sdb.add_edge("a", "b", "similar")
    assert sdb.c.execute("select count(*) from edges").fetchone()[0] == 1
    sdb.log_check("a", "ok")
    assert sdb.c.execute("select count(*) from checks").fetchone()[0] == 1
```
`tests/sources/conftest.py`:
```python
import pytest
from reels_radar.sources.db import SourcesDB


@pytest.fixture
def sdb(tmp_path):
    return SourcesDB(tmp_path / "s.db")
```
- [ ] **Step 2: Run** `uv run pytest tests/sources -q` → Expected: ImportError.
- [ ] **Step 3: Implement** `reels_radar/sources/db.py`:
```python
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  username TEXT PRIMARY KEY, platform TEXT NOT NULL DEFAULT 'instagram',
  status TEXT NOT NULL DEFAULT 'candidate', intent TEXT NOT NULL DEFAULT 'none',
  themes TEXT, priority REAL NOT NULL DEFAULT 0, value_score REAL, posts_per_week REAL,
  last_post_at TEXT, posts_visible INTEGER, followers INTEGER, bio TEXT, why TEXT,
  suggest_cleanup INTEGER NOT NULL DEFAULT 0, reviewed INTEGER NOT NULL DEFAULT 0,
  followed INTEGER NOT NULL DEFAULT 0, saved_count INTEGER NOT NULL DEFAULT 0,
  depth INTEGER NOT NULL DEFAULT 0, notes TEXT,
  first_seen TEXT, last_checked TEXT, next_check TEXT
);
CREATE INDEX IF NOT EXISTS acc_status ON accounts(status);
CREATE TABLE IF NOT EXISTS edges (parent TEXT NOT NULL, child TEXT NOT NULL, kind TEXT NOT NULL,
  PRIMARY KEY (parent, child, kind));
CREATE TABLE IF NOT EXISTS checks (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
  ts TEXT NOT NULL, result TEXT NOT NULL);
"""

FIELDS = {"status", "intent", "themes", "priority", "value_score", "posts_per_week", "last_post_at",
          "posts_visible", "followers", "bio", "why", "suggest_cleanup", "reviewed", "followed",
          "saved_count", "depth", "notes", "first_seen", "last_checked", "next_check"}


def norm(username) -> str:
    return (username or "").strip().lstrip("@").strip().lower()


class SourcesDB:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(str(path))
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)

    def upsert(self, username, **fields) -> bool:
        u = norm(username)
        bad = set(fields) - FIELDS
        if bad:
            raise KeyError(f"unknown fields: {bad}")
        if not u:
            return False
        created = self.c.execute("SELECT 1 FROM accounts WHERE username=?", (u,)).fetchone() is None
        if created:
            self.c.execute("INSERT INTO accounts(username, first_seen) VALUES(?,?)",
                           (u, datetime.now().isoformat()))
        if fields:
            sets = ",".join(f"{k}=?" for k in fields)
            self.c.execute(f"UPDATE accounts SET {sets} WHERE username=?", (*fields.values(), u))
        self.c.commit()
        return created

    def update(self, username, **fields):
        self.upsert(username, **fields)

    def get(self, username):
        return self.c.execute("SELECT * FROM accounts WHERE username=?", (norm(username),)).fetchone()

    def by_status(self, status, limit=1000):
        return self.c.execute("SELECT * FROM accounts WHERE status=? LIMIT ?", (status, limit)).fetchall()

    def counts(self) -> dict[str, int]:
        return {r[0]: r[1] for r in self.c.execute("SELECT status, COUNT(*) FROM accounts GROUP BY status")}

    def add_edge(self, parent, child, kind):
        p, ch = norm(parent), norm(child)
        if p and ch:
            self.c.execute("INSERT OR IGNORE INTO edges(parent,child,kind) VALUES(?,?,?)", (p, ch, kind))
            self.c.commit()

    def log_check(self, username, result):
        self.c.execute("INSERT INTO checks(username,ts,result) VALUES(?,?,?)",
                       (norm(username), datetime.now().isoformat(), result))
        self.c.commit()
```
Пустые `__init__.py` в `reels_radar/sources/` и `tests/sources/`.
- [ ] **Step 4: Run** → Expected: `5 passed`.
- [ ] **Step 5: Commit** `git add -A && git commit -m "feat(sources): SourcesDB"`.

---

### Task 2: Импорт подписок, авторов сохранёнок, дат постов

**Files:** Create `reels_radar/sources/importers.py`; Test `tests/sources/test_importers.py`

**Interfaces:**
- Consumes: `SourcesDB`, `norm`; `reels_radar.export.parse_export`.
- Produces: `import_following(sdb, path) -> int` (новых аккаунтов; формат `relationships_following`, `title` = юзернейм, `string_list_data[0].timestamp` → не используется), `import_saved_authors(sdb, items_by_key_path, theme_map_path, export_dir) -> int` (новых аккаунтов; `saved_count` и `themes` выставляются **абсолютными** значениями пересчёта, `reviewed` и статусы не трогаются), `import_last_posts(sdb, jsonl_path) -> int` (обновлённых).

- [ ] **Step 1: Failing test** `tests/sources/test_importers.py`:
```python
import json
from reels_radar.sources.importers import import_following, import_saved_authors, import_last_posts


def write(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False))


def test_import_following_dedups_case_and_empty(tmp_path, sdb):
    f = tmp_path / "following.json"
    write(f, {"relationships_following": [
        {"title": "Bob", "string_list_data": [{"timestamp": 1}]},
        {"title": "bob"}, {"title": ""}, {"nope": 1}, {"title": "alice"}]})
    assert import_following(sdb, f) == 2
    assert sdb.get("bob")["followed"] == 1
    assert import_following(sdb, f) == 0


def test_reimport_keeps_manual_marks(tmp_path, sdb):
    f = tmp_path / "following.json"
    write(f, {"relationships_following": [{"title": "bob"}]})
    import_following(sdb, f)
    sdb.update("bob", reviewed=1, intent="cleanup", status="personal")
    import_following(sdb, f)
    r = sdb.get("bob")
    assert r["reviewed"] == 1 and r["intent"] == "cleanup" and r["status"] == "personal"


def test_import_saved_authors_counts_and_top_theme(tmp_path, sdb):
    ik, tm = tmp_path / "ik.json", tmp_path / "tm.json"
    write(ik, {"001": {"author": "Carol"}, "002": {"author": "carol"}, "003": {"author": "carol"}, "004": {"author": "dave"}, "005": {}})
    write(tm, {"001": "ИИ", "002": "Карьера", "003": "ИИ", "004": "Вьетнам"})
    exp = tmp_path / "exp"; exp.mkdir()
    assert import_saved_authors(sdb, ik, tm, exp) == 2
    c = sdb.get("carol")
    assert c["saved_count"] == 3 and c["themes"] == "ИИ"
    assert import_saved_authors(sdb, ik, tm, exp) == 0
    assert sdb.get("carol")["saved_count"] == 3


def test_import_last_posts(tmp_path, sdb):
    j = tmp_path / "lp.jsonl"
    j.write_text('{"u":"Bob","lastPost":"2019-03-01T10:00:00.000Z"}\n'
                 '{"u":"empty","lastPost":null,"note":"no_posts_found_or_private"}\n\nnot json\n')
    assert import_last_posts(sdb, j) == 2
    assert sdb.get("bob")["last_post_at"].startswith("2019-03-01") and sdb.get("bob")["posts_visible"] == 1
    assert sdb.get("empty")["posts_visible"] == 0 and sdb.get("empty")["last_post_at"] is None
```
- [ ] **Step 2: Run** → Expected: ImportError.
- [ ] **Step 3: Implement** `reels_radar/sources/importers.py`:
```python
from __future__ import annotations

import collections
import json
from pathlib import Path

from ..export import parse_export
from .db import SourcesDB, norm


def import_following(sdb: SourcesDB, path) -> int:
    data = json.load(open(path)).get("relationships_following", [])
    new = 0
    for x in data:
        u = norm(x.get("title") if isinstance(x, dict) else "")
        if not u:
            continue
        new += sdb.upsert(u, followed=1)
    return new


def import_saved_authors(sdb: SourcesDB, items_by_key_path, theme_map_path, export_dir) -> int:
    counts: collections.Counter = collections.Counter()
    themes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    ik = json.load(open(items_by_key_path)) if Path(items_by_key_path).exists() else {}
    tm = json.load(open(theme_map_path)) if Path(theme_map_path).exists() else {}
    for key, v in ik.items():
        a = norm(v.get("author") if isinstance(v, dict) else "")
        if a:
            counts[a] += 1
            if key in tm:
                themes[a][tm[key]] += 1
    for it in parse_export(Path(export_dir)):
        a = norm(it.owner)
        if a:
            counts[a] += 1
    new = 0
    for a, n in counts.items():
        fields = {"saved_count": n}
        if themes[a]:
            fields["themes"] = themes[a].most_common(1)[0][0]
        new += sdb.upsert(a, **fields)
        sdb.add_edge("me", a, "saved_author")
    return new


def import_last_posts(sdb: SourcesDB, jsonl_path) -> int:
    n = 0
    for line in open(jsonl_path):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        u = norm(r.get("u"))
        if not u:
            continue
        lp = r.get("lastPost")
        sdb.upsert(u, last_post_at=lp, posts_visible=1 if lp else 0)
        n += 1
    return n
```
Примечание: пересчёт `saved_count` абсолютным значением: повторный импорт тех же файлов даёт то же число, а не удвоение. Если один и тот же рилс есть и в старом `items_by_key`, и в новом экспорте, он считается дважды: допустимо, `saved_count` используется только как признак «сохранял с него» (`> 0`).
- [ ] **Step 4: Run** → Expected: `4 passed` в этом файле.
- [ ] **Step 5: Commit** `feat(sources): importers`.

---

### Task 3: Правила чистки

**Files:** Create `reels_radar/sources/cleanup.py`; Test `tests/sources/test_cleanup.py`

**Interfaces:**
- Consumes: `SourcesDB`.
- Produces: `suggest_cleanup(sdb, now: datetime, years: int = 2) -> int` (число новых предложений), `candidates(sdb, limit=10, offset=0) -> list[Row]` (suggest_cleanup=1 и reviewed=0; сначала самые давние с датой, затем без постов), `marked(sdb) -> list[Row]` (intent=cleanup, followed=1, status != ignored).

- [ ] **Step 1: Failing test** `tests/sources/test_cleanup.py`:
```python
from datetime import datetime
from reels_radar.sources.cleanup import suggest_cleanup, candidates, marked

NOW = datetime(2026, 10, 17)


def acc(sdb, u, last=None, visible=1, **kw):
    sdb.upsert(u, followed=1, last_post_at=last, posts_visible=visible, **kw)


def test_old_and_empty_are_suggested(sdb):
    acc(sdb, "old", "2019-03-01T00:00:00.000Z")
    acc(sdb, "fresh", "2026-09-01T00:00:00.000Z")
    acc(sdb, "empty", None, visible=0)
    assert suggest_cleanup(sdb, NOW) == 2
    assert sdb.get("old")["suggest_cleanup"] == 1 and "2019-03-01" in sdb.get("old")["why"]
    assert sdb.get("fresh")["suggest_cleanup"] == 0
    assert "нет видимых постов" in sdb.get("empty")["why"]


def test_protected_accounts_never_suggested(sdb):
    acc(sdb, "saved", "2019-01-01T00:00:00.000Z", saved_count=2)
    acc(sdb, "friend", "2019-01-01T00:00:00.000Z", status="personal")
    acc(sdb, "keeper", "2019-01-01T00:00:00.000Z", reviewed=1)
    acc(sdb, "unknown_date", None, visible=None)
    assert suggest_cleanup(sdb, NOW) == 0


def test_not_followed_never_suggested(sdb):
    sdb.upsert("x", followed=0, last_post_at="2018-01-01T00:00:00.000Z", posts_visible=1)
    assert suggest_cleanup(sdb, NOW) == 0


def test_candidates_order_and_paging(sdb):
    acc(sdb, "b", "2020-01-01T00:00:00.000Z"); acc(sdb, "a", "2018-01-01T00:00:00.000Z")
    acc(sdb, "z", None, visible=0)
    suggest_cleanup(sdb, NOW)
    assert [r["username"] for r in candidates(sdb, 10)] == ["a", "b", "z"]
    assert [r["username"] for r in candidates(sdb, 1, offset=1)] == ["b"]


def test_marked(sdb):
    acc(sdb, "a"); acc(sdb, "b")
    sdb.update("a", intent="cleanup")
    assert [r["username"] for r in marked(sdb)] == ["a"]
```
- [ ] **Step 2: Run** → Expected: ImportError.
- [ ] **Step 3: Implement:**
```python
from __future__ import annotations

from datetime import datetime

from .db import SourcesDB


def suggest_cleanup(sdb: SourcesDB, now: datetime, years: int = 2) -> int:
    cutoff = now.replace(year=now.year - years).strftime("%Y-%m-%d")
    rows = sdb.c.execute(
        "SELECT username, last_post_at, posts_visible FROM accounts "
        "WHERE followed=1 AND status!='personal' AND saved_count=0 AND reviewed=0 AND suggest_cleanup=0").fetchall()
    n = 0
    for r in rows:
        why = None
        if r["last_post_at"] and r["last_post_at"][:10] < cutoff:
            why = f"последний пост {r['last_post_at'][:10]}"
        elif r["posts_visible"] == 0:
            why = "нет видимых постов (закрытый или пустой)"
        if why:
            sdb.update(r["username"], suggest_cleanup=1, why=why)
            n += 1
    return n


def candidates(sdb: SourcesDB, limit: int = 10, offset: int = 0):
    return sdb.c.execute(
        "SELECT * FROM accounts WHERE suggest_cleanup=1 AND reviewed=0 "
        "ORDER BY (last_post_at IS NULL), last_post_at ASC, username LIMIT ? OFFSET ?",
        (limit, offset)).fetchall()


def marked(sdb: SourcesDB):
    return sdb.c.execute(
        "SELECT * FROM accounts WHERE intent='cleanup' AND followed=1 AND status!='ignored' "
        "ORDER BY (last_post_at IS NULL), last_post_at ASC, username").fetchall()
```
- [ ] **Step 4: Run** → Expected: `5 passed`.
- [ ] **Step 5: Commit** `feat(sources): cleanup rules`.

---

### Task 4: Действия над аккаунтом и карточки

**Files:** Modify `reels_radar/sources/cleanup.py` (добавить `apply_action`, `export_cleanup`); Create `reels_radar/sources/cards.py`; Test `tests/sources/test_actions.py`

**Interfaces:**
- Produces: `apply_action(sdb, username, action) -> str`, где action ∈ `del | keep | personal | done`: `del` → `intent=cleanup, reviewed=1`; `keep` → `intent=none, reviewed=1, suggest_cleanup=0`; `personal` → `status=personal, intent=none, reviewed=1, suggest_cleanup=0`; `done` → `status=ignored, followed=0` (intent остаётся `cleanup`). Любое действие идемпотентно, последнее решение побеждает, кроме `done` (оно финально). `export_cleanup(sdb, path) -> int`. `account_text(row) -> str`, `account_keyboard(username) -> list[list[tuple[str,str]]]`, `parse_account_cb(data) -> tuple[str,str]`.

- [ ] **Step 1: Failing test** `tests/sources/test_actions.py`:
```python
from reels_radar.sources.cleanup import apply_action, export_cleanup
from reels_radar.sources.cards import account_text, account_keyboard, parse_account_cb


def acc(sdb, u, **kw):
    sdb.upsert(u, followed=1, last_post_at="2019-03-01T00:00:00.000Z", posts_visible=1, **kw)


def test_del_then_keep_last_wins(sdb):
    acc(sdb, "a")
    apply_action(sdb, "a", "del"); apply_action(sdb, "a", "del")
    assert sdb.get("a")["intent"] == "cleanup" and sdb.get("a")["reviewed"] == 1
    apply_action(sdb, "a", "keep")
    assert sdb.get("a")["intent"] == "none"


def test_personal_blocks_cleanup(sdb):
    acc(sdb, "a")
    apply_action(sdb, "a", "personal")
    r = sdb.get("a")
    assert r["status"] == "personal" and r["intent"] == "none" and r["suggest_cleanup"] == 0


def test_done_is_final(sdb):
    acc(sdb, "a")
    apply_action(sdb, "a", "del"); apply_action(sdb, "a", "done")
    r = sdb.get("a")
    assert r["status"] == "ignored" and r["followed"] == 0
    apply_action(sdb, "a", "keep")
    assert sdb.get("a")["status"] == "ignored"


def test_export_cleanup(tmp_path, sdb):
    acc(sdb, "a", why="последний пост 2019-03-01"); acc(sdb, "b")
    apply_action(sdb, "a", "del")
    p = tmp_path / "cleanup.txt"
    assert export_cleanup(sdb, p) == 1
    text = p.read_text()
    assert "a" in text and "2019-03-01" in text and "b" not in text.split()[0:1] and "—" not in text


def test_callback_roundtrip_with_dots_and_underscores():
    for u in ("john.doe_99", "a" * 30, "x.y.z"):
        for _, data in account_keyboard(u)[0]:
            action, name = parse_account_cb(data)
            assert name == u and action in {"del", "keep", "personal"}
            assert len(data.encode()) <= 64


def test_account_text(sdb):
    acc(sdb, "a", why="последний пост 2019-03-01")
    t = account_text(sdb.get("a"))
    assert "@a" in t and "2019-03-01" in t and "—" not in t
```
- [ ] **Step 2: Run** → Expected: ImportError (apply_action, cards).
- [ ] **Step 3: Implement.** Дописать в `cleanup.py`:
```python
from pathlib import Path


def apply_action(sdb: SourcesDB, username: str, action: str) -> str:
    r = sdb.get(username)
    if r is None:
        return "аккаунт не найден"
    if r["status"] == "ignored":
        return "уже отписан"
    if action == "del":
        sdb.update(username, intent="cleanup", reviewed=1)
        return "на удаление"
    if action == "keep":
        sdb.update(username, intent="none", reviewed=1, suggest_cleanup=0)
        return "оставлен"
    if action == "personal":
        sdb.update(username, status="personal", intent="none", reviewed=1, suggest_cleanup=0)
        return "личный"
    if action == "done":
        sdb.update(username, status="ignored", followed=0)
        return "отписан"
    raise ValueError(f"unknown action {action}")


def export_cleanup(sdb: SourcesDB, path) -> int:
    rows = marked(sdb)
    lines = [f"{r['username']} - {r['why'] or 'без причины'}" for r in rows]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf8")
    return len(rows)
```
`reels_radar/sources/cards.py`:
```python
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
```
- [ ] **Step 4: Run** `uv run pytest tests/sources -q` → Expected: все зелёные.
- [ ] **Step 5: Commit** `feat(sources): actions, export, account cards`.

---

### Task 5: Команды бота

**Files:** Modify `reels_radar/bot.py`, `reels_radar/config.py`, `config/settings.yaml`; Test `tests/sources/test_bot_pure.py`

**Interfaces:**
- Consumes: Task 1-4.
- Produces: в `router(s, db, themes, sdb=None)`: `/cleanup` (шлёт до 10 карточек кандидатов, на каждую отдельное сообщение с клавиатурой), callback `ac:` (применяет `apply_action`, убирает клавиатуру, `answer` с результатом), `/cleanup_list` (список `marked` порциями до 3500 символов + пишет `data/cleanup.txt`), `/done user1 user2 ...` (apply_action `done` для каждого). `run_bot(s, db, themes)` создаёт `SourcesDB(s.data_dir / "sources.db")`. Чистая функция `chunk_lines(lines, limit=3500) -> list[str]` в `reels_radar/sources/cards.py`, тестируется.

- [ ] **Step 1: Failing test** `tests/sources/test_bot_pure.py`:
```python
from reels_radar.sources.cards import chunk_lines


def test_chunk_lines_respects_limit_and_keeps_order():
    lines = [f"user{i} - причина" for i in range(500)]
    chunks = chunk_lines(lines, limit=200)
    assert all(len(c) <= 200 for c in chunks)
    assert "\n".join(chunks).split("\n") == lines


def test_chunk_lines_empty():
    assert chunk_lines([]) == []
```
- [ ] **Step 2: Run** → Expected: ImportError.
- [ ] **Step 3: Implement.** В `cards.py` добавить:
```python
def chunk_lines(lines: list[str], limit: int = 3500) -> list[str]:
    out, cur = [], ""
    for ln in lines:
        add = (ln if not cur else "\n" + ln)
        if cur and len(cur) + len(add) > limit:
            out.append(cur)
            cur = ln
        else:
            cur += add
    if cur:
        out.append(cur)
    return out
```
В `bot.py` внутри `router` добавить параметр `sdb=None` и хендлеры (aiogram, по образцу существующих; импорты `from .sources.cleanup import apply_action as acc_action, candidates, export_cleanup, marked`, `from .sources.cards import account_keyboard, account_text, chunk_lines, parse_account_cb`):
```python
    def akb(u):
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
                                                     for row in account_keyboard(u)])

    @rt.message(Command("cleanup"), owner)
    async def cleanup(m: Message):
        rows = candidates(sdb, 10)
        if not rows:
            await m.answer("кандидатов на чистку нет")
        for r in rows:
            await m.answer(account_text(r), reply_markup=akb(r["username"]))

    @rt.callback_query(F.data.startswith("ac:"), owner)
    async def acb(q: CallbackQuery):
        action, user = parse_account_cb(q.data)
        msg = acc_action(sdb, user, action)
        await q.message.edit_reply_markup(reply_markup=None)
        await q.answer(msg)

    @rt.message(Command("cleanup_list"), owner)
    async def clist(m: Message):
        export_cleanup(sdb, s.data_dir / "cleanup.txt")
        lines = [f"{r['username']} - {r['why'] or ''}".strip(" -") for r in marked(sdb)]
        for part in chunk_lines(lines) or ["список пуст"]:
            await m.answer(part)

    @rt.message(Command("done"), owner)
    async def done(m: Message):
        users = (m.text or "").split()[1:]
        await m.answer(", ".join(f"{u}: {acc_action(sdb, u, 'done')}" for u in users) or "укажи юзернеймы")
```
ВАЖНО: существующий `@rt.callback_query(owner)` в `router` перехватит `ac:` раньше: зарегистрировать новый хендлер `ac:` **до** него, а в существующем в начале ветки `parse_callback` оставить как есть (он не вызывается для `ac:`, так как aiogram вызывает первый подошедший хендлер). `run_bot`: `sdb = SourcesDB(s.data_dir / "sources.db")` и `router(s, db, themes, sdb)`. Настройки в `config.py` не меняются в этом task (пути к файлам импорта берёт CLI, Task 6).
- [ ] **Step 4: Run** `uv run pytest -q` → Expected: все зелёные; `uv run python -c "import reels_radar.bot"` → без ошибок.
- [ ] **Step 5: Commit** `feat(sources): bot cleanup commands`.

---

### Task 6: CLI и живой импорт

**Files:** Modify `reels_radar/cli.py`, `config/settings.yaml`, `reels_radar/config.py`, `tests/test_config.py`; Test `tests/sources/test_cli_sources.py`

**Interfaces:**
- Produces: `settings.yaml`: `last_posts_file: /Users/cucaramba/Claude Code/tmp/ig_last_post_dates.jsonl`, `cleanup_years: 2`; `Settings.last_posts_file: Path`, `Settings.cleanup_years: int`. CLI: `sources import --export DIR` (following.json найден рекурсивно в DIR, `import_saved_authors`, `import_last_posts`), `sources suggest`, `sources export`, `sources stats`; все печатают числа.

- [ ] **Step 1: Failing test** `tests/sources/test_cli_sources.py`:
```python
import json
from pathlib import Path
from reels_radar.cli import main

PROJECT = Path(__file__).resolve().parent.parent.parent


def test_sources_import_suggest_export(tmp_path, monkeypatch, capsys):
    exp = tmp_path / "exp"; (exp / "connections").mkdir(parents=True)
    (exp / "connections" / "following.json").write_text(json.dumps({"relationships_following": [{"title": "old"}, {"title": "fresh"}]}))
    lp = tmp_path / "lp.jsonl"
    lp.write_text('{"u":"old","lastPost":"2019-01-01T00:00:00.000Z"}\n{"u":"fresh","lastPost":"2026-10-01T00:00:00.000Z"}\n')
    (tmp_path / "config").mkdir()
    cfg = (PROJECT / "config" / "settings.yaml").read_text()
    import re
    cfg = re.sub(r"last_posts_file: .*", f"last_posts_file: {lp}", cfg)
    cfg = re.sub(r"reels_pipeline: .*", f"reels_pipeline: {tmp_path}", cfg)
    (tmp_path / "config" / "settings.yaml").write_text(cfg)
    (tmp_path / "config" / "themes.yaml").write_text((PROJECT / "config" / "themes.yaml").read_text())
    monkeypatch.setenv("REELS_RADAR_ROOT", str(tmp_path))
    assert main(["sources", "import", "--export", str(exp)]) == 0
    assert main(["sources", "suggest"]) == 0
    out = capsys.readouterr().out
    assert "подписок новых: 2" in out and "предложено на чистку: 1" in out
    from reels_radar.sources.db import SourcesDB
    sdb = SourcesDB(tmp_path / "data" / "sources.db")
    assert sdb.get("old")["suggest_cleanup"] == 1 and sdb.get("fresh")["suggest_cleanup"] == 0
```
В `tests/test_config.py` ничего не меняется, если новые поля читаются с дефолтами (см. Step 3).
- [ ] **Step 2: Run** → Expected: SystemExit/ошибка парсинга аргументов.
- [ ] **Step 3: Implement.** `config.py`: в `Settings` добавить `last_posts_file: Path` и `cleanup_years: int`; в `load_settings`: `last_posts_file=Path(y.get("last_posts_file", "")), cleanup_years=int(y.get("cleanup_years", 2))`. `settings.yaml` дописать две строки. В `cli.py`: подпарсер `sources` с вложенным `import|suggest|export|stats`:
```python
    sp = sub.add_parser("sources"); ssub = sp.add_subparsers(dest="scmd", required=True)
    pi = ssub.add_parser("import"); pi.add_argument("--export", required=True)
    for n in ("suggest", "export", "stats"):
        ssub.add_parser(n)
```
и обработка (до `db = DB(...)` не нужна):
```python
    if a.cmd == "sources":
        from datetime import datetime as _dt
        from .sources.cleanup import export_cleanup, suggest_cleanup
        from .sources.db import SourcesDB
        from .sources.importers import import_following, import_last_posts, import_saved_authors
        sdb = SourcesDB(s.data_dir / "sources.db")
        if a.scmd == "import":
            fol = next(Path(a.export).rglob("following.json"), None)
            print("подписок новых:", import_following(sdb, fol) if fol else 0)
            print("авторов сохранёнок новых:", import_saved_authors(
                sdb, s.reels_pipeline / "items_by_key.json", s.reels_pipeline / "final_theme_map.json", a.export))
            print("дат постов обновлено:", import_last_posts(sdb, s.last_posts_file) if s.last_posts_file.is_file() else 0)
        elif a.scmd == "suggest":
            print("предложено на чистку:", suggest_cleanup(sdb, _dt.now(), s.cleanup_years))
        elif a.scmd == "export":
            print("в списке на удаление:", export_cleanup(sdb, s.data_dir / "cleanup.txt"))
        else:
            print(sdb.counts())
        return 0
```
Блок вставляется сразу после `s, themes = load_settings(r), load_themes(r)`.
- [ ] **Step 4: Run** `uv run pytest -q` → Expected: все зелёные.
- [ ] **Step 5: Живой импорт (не TDD):** `uv run python -m reels_radar sources import --export ~/Downloads/сохраненное2`, затем `sources suggest`, `sources stats`. Записать числа в HANDOFF. Ожидание по данным: ~2466 подписок, ~1565+ авторов сохранёнок, предложений на чистку порядка 200-700 (старые 194 в `ig_dead_2plus`: сверить).
- [ ] **Step 6: Commit** `feat(sources): cli import/suggest/export`.

---

### Task 7: Запуск в боте

- [ ] **Step 1:** Перезапустить бота (`kill` процесса python, не только обёртки `uv`; проверить `pgrep -fl "reels_radar bot"`), чтобы подхватил `/cleanup`.
- [ ] **Step 2:** Некит присылает `/cleanup`, жмёт 🗑/✅/👤 на 10 карточках. Проверить в `sources.db`: `intent`, `reviewed`, `status`.
- [ ] **Step 3:** `/cleanup_list` выдаёт список, файл `data/cleanup.txt` создан. Некит отписывается вручную, шлёт `/done user1 user2`, статусы становятся `ignored`.
- [ ] **Step 4:** Обновить `HANDOFF.md`: числа импорта, команды, что дальше (S1 спайк, S3 классификация).
- [ ] **Step 5: Commit** `docs: handoff sources S2`.

---

## Self-Review

**Spec coverage (S2):** реестр с полями `intent` и `suggest_cleanup` (Task 1) ✓; импорт подписок, авторов сохранёнок, дат (Task 2) ✓; правила чистки и исключения personal/saved (Task 3) ✓; действия 🗑 ✅ 👤 и итоговый список (Task 4) ✓; `/cleanup`, `/cleanup_list`, `/done` (Task 5) ✓; CLI (Task 6) ✓. Кнопки ⏸ и ❌ для harvest-карточек и карточки кандидатов расширения графа относятся к S3-S4 и сюда не входят (отклонение, осознанное: S2 даёт пользу чистки без запросов к Instagram).

**Placeholder scan:** заглушек нет. Task 7 Step 5 содержит ожидание порядка величин, это не заглушка кода, а проверка на живых данных.

**Type consistency:** `SourcesDB.upsert/update/get/by_status`, `norm` одинаковы везде. `apply_action(sdb, username, action)` в Task 4 вызывается так же в Task 5 (импортирован как `acc_action`). `candidates/marked/export_cleanup/suggest_cleanup` совпадают в Task 3, 4, 5, 6. Callback `ac:<action>:<username>` формируется в `account_keyboard` и разбирается `parse_account_cb` (split по первым двум двоеточиям) ✓.

**Review Focus:** покрыты тестами: пустой/null юзернейм и регистр (Task 1-2), повторный импорт и ручные пометки (Task 2), personal и saved не предлагаются (Task 3), двойной 🗑 и смена решения (Task 4), юзернеймы с `.` `_` в callback (Task 4).

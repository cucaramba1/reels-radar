# Reels Radar Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ночной конвейер: экспорт Instagram → отсев повторов → видео + расшифровка + OCR → отбор → анализ кадров через `claude -p` → карточки в Telegram-боте → заметки в Obsidian и недельный дайджест.

**Architecture:** Отдельный Python-проект `~/Claude Code/reels-radar/`, очередь и статусы в SQLite (stdlib `sqlite3`), каждый шаг возобновляем и принимает внешние зависимости параметром (fetcher, claude), чтобы тестироваться без сети. Бот на aiogram тонкий: вся логика в чистых модулях `cards.py` и `review.py`.

**Tech Stack:** Python 3.12, uv, aiogram>=3.31, pyyaml, python-dotenv, pytest. Внешние бинарники (уже стоят): `yt-dlp`, `gallery-dl`, `ffmpeg`, `~/Claude Code/tools/reels/ocr`, `~/.local/share/uv/tools/mlx-whisper/bin/mlx_whisper`, `claude`.

**Spec:** `docs/superpowers/specs/2026-10-16-reels-radar-core-design.md`

## Global Constraints

- Свободное место меньше 10 ГБ допустимо, но видео и кадры живут только на время шага и удаляются сразу (`shutil.rmtree`).
- В заметках vault нет авторов, имён каналов, юзернеймов. Ссылка на оригинал только в SQLite.
- Без длинного тире (—) в текстах для людей: карточки, заметки, дайджест.
- Темы и папки vault только из `config/themes.yaml`, в коде тем нет.
- Рилс с речью не уходит в `archived` без расшифровки: при `no_video` остаётся в очереди.
- Живой vault (`~/Documents/Obsidian storage`) в тестах не трогать, только `tmp_path`.
- Удаление заметок = перенос в `<vault>/.trash/` с сохранением относительного пути, не `rm`.
- Коммиты с трейлером `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Ветка `feat/core`, `main` не трогаем до финального ревью.

## Review Focus

- Экспорт без поля «Описание» или с пустым URL: запись пропускается, парсер не падает (Task 2).
- Тот же рилс в двух экспортах и в старом `items_by_key.json`: не создаёт вторую карточку (Task 3).
- Видео не скачалось ни одним способом: рилс остаётся `no_video`, не `archived` и не `failed` навсегда (Task 4, 8).
- `claude -p` отвечает мусором или упирается в лимит: карточка не создаётся, очередь не теряется, лимит ставит паузу (Task 6, 8).
- Заголовок заметки с `/`, `:` или дублем существующей: файл не создаётся вне папки темы, существующая заметка не перезаписывается (Task 7).

---

## File Structure

```
reels-radar/
  pyproject.toml
  .env.example
  config/settings.yaml          пороги, пути, лимиты
  config/themes.yaml            темы -> папка vault, MOC
  reels_radar/
    __init__.py
    config.py                   Settings, load_settings, load_themes
    db.py                       DB: items, kv, writes
    export.py                   parse_export
    dedup.py                    known_codes, filter_new
    fetch.py                    fetchers + chain
    local.py                    frames, ocr, whisper, score
    claude.py                   run_claude
    vision.py                   build_prompt, SCHEMA, classify
    cards.py                    render_card, keyboard_spec, parse_callback
    review.py                   apply_action
    vault.py                    write_note, rollback_note
    digest.py                   build_digest
    pipeline.py                 run_batch
    bot.py                      aiogram handlers, tick
    cli.py                      ingest | run | digest | bot
  scripts/pw_fetch.py           Playwright-перехват URL медиа (запасной путь)
  tests/                        по файлу на модуль
```

---

### Task 1: Каркас, конфиг, БД

**Files:**
- Create: `pyproject.toml`, `.env.example`, `config/settings.yaml`, `config/themes.yaml`
- Create: `reels_radar/__init__.py`, `reels_radar/config.py`, `reels_radar/db.py`
- Test: `tests/test_config.py`, `tests/test_db.py`, `tests/conftest.py`, `tests/__init__.py`

**Interfaces:**
- Produces: `Settings` (dataclass), `load_settings(root: Path) -> Settings`, `Theme` (dataclass: `name, folder, moc`), `load_themes(root) -> dict[str, Theme]`; `DB(path)` с методами `add_item(code, url, caption, ts, folder=None) -> bool`, `get(code) -> sqlite3.Row | None`, `by_status(status, limit=100) -> list[Row]`, `update(code, **fields)`, `counts() -> dict[str,int]`, `kv_get(key, default=None)`, `kv_set(key, value)`.
- Статусы item: `new, no_video, failed, archived, local, draft, approved, rejected, written`.

- [ ] **Step 1: pyproject и каркас**

`pyproject.toml`:
```toml
[project]
name = "reels-radar"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["aiogram>=3.31.0", "python-dotenv>=1.2.4", "pyyaml>=6.0.3"]

[dependency-groups]
dev = ["pytest>=9.1.1"]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

`.env.example`:
```
BOT_TOKEN=
OWNER_ID=
VAULT=/Users/cucaramba/Documents/Obsidian storage
```

`config/settings.yaml`:
```yaml
data_dir: data
reels_tools: /Users/cucaramba/Claude Code/tools/reels
reels_pipeline: /Users/cucaramba/Claude Code/reels_pipeline
claude_bin: claude
whisper_bin: /Users/cucaramba/.local/share/uv/tools/mlx-whisper/bin/mlx_whisper
whisper_model: mlx-community/whisper-large-v3-turbo
select_threshold: 30
max_frames: 6
batch_size: 20
min_free_gb: 3
claude_timeout: 300
keywords: [claude, клод, mcp, скилл, промпт, монтаж, съёмка, хук, нячанг, йога, продуктивность]
```

`config/themes.yaml` (папки заменить на реальные из vault при Task 11, пока имена-кандидаты):
```yaml
themes:
  Психология и саморазвитие: {folder: "Психология и саморазвитие", moc: "Психология и саморазвитие — карта заметок.md"}
  ИИ: {folder: "ИИ работа", moc: "ИИ работа — карта заметок.md"}
  Вьетнам: {folder: "Вьетнам", moc: "Вьетнам — карта заметок.md"}
  Фитнес и здоровье: {folder: "Фитнес и здоровье", moc: "Фитнес и здоровье — карта заметок.md"}
  Юмор и развлечения: {folder: "Юмор и развлечения", moc: "Юмор и развлечения — карта заметок.md"}
  Карьера: {folder: "Карьера", moc: "Карьера — карта заметок.md"}
  Путешествия: {folder: "Путешествия", moc: "Путешествия — карта заметок.md"}
  Дом и сетапы: {folder: "Дом и сетапы", moc: "Дом и сетапы — карта заметок.md"}
  Финансы и трейдинг: {folder: "Финансы и трейдинг", moc: "Финансы и трейдинг — карта заметок.md"}
  Кулинария: {folder: "Кулинария", moc: "Кулинария — карта заметок.md"}
  Маркетплейсы: {folder: "Маркетплейсы", moc: "Маркетплейсы — карта заметок.md"}
  Съёмка и монтаж: {folder: "Контент и соцсети", moc: "Контент и соцсети — карта заметок.md"}
  Слова и фразы: {folder: "Слова и фразы", moc: "Слова и фразы — карта заметок.md"}
  Разное: {folder: "Разное", moc: "Разное — карта заметок.md"}
```

`tests/conftest.py`:
```python
import pytest
from reels_radar.db import DB


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "t.db")
```

- [ ] **Step 2: Failing tests**

`tests/test_db.py`:
```python
def test_add_item_is_idempotent(db):
    assert db.add_item("AAA", "https://i/reel/AAA/", "cap", 100) is True
    assert db.add_item("AAA", "https://i/reel/AAA/", "cap", 100) is False
    assert db.get("AAA")["status"] == "new"


def test_update_and_by_status(db):
    db.add_item("AAA", "u", "c", 1)
    db.update("AAA", status="local", score=55.0, transcript="текст")
    assert [r["code"] for r in db.by_status("local")] == ["AAA"]
    assert db.get("AAA")["score"] == 55.0
    assert db.counts() == {"local": 1}


def test_kv(db):
    assert db.kv_get("x", "d") == "d"
    db.kv_set("x", "1")
    assert db.kv_get("x") == "1"
```

`tests/test_config.py`:
```python
from pathlib import Path
from reels_radar.config import load_settings, load_themes

ROOT = Path(__file__).resolve().parent.parent


def test_load_settings_and_themes():
    s = load_settings(ROOT)
    assert s.select_threshold == 30 and s.max_frames == 6
    themes = load_themes(ROOT)
    assert "Съёмка и монтаж" in themes and "Слова и фразы" in themes
    assert themes["ИИ"].folder
```

- [ ] **Step 3: Run, expect FAIL** — `uv run pytest -q` → ImportError.

- [ ] **Step 4: Implement**

`reels_radar/config.py`:
```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass(frozen=True)
class Theme:
    name: str
    folder: str
    moc: str


@dataclass
class Settings:
    root: Path
    data_dir: Path
    vault: Path
    bot_token: str
    owner_id: int
    reels_tools: Path
    reels_pipeline: Path
    claude_bin: str
    whisper_bin: str
    whisper_model: str
    select_threshold: float
    max_frames: int
    batch_size: int
    min_free_gb: float
    claude_timeout: int
    keywords: list[str]


def load_settings(root: Path) -> Settings:
    load_dotenv(root / ".env")
    y = yaml.safe_load((root / "config" / "settings.yaml").read_text())
    return Settings(
        root=root,
        data_dir=root / y["data_dir"],
        vault=Path(os.environ.get("VAULT", "")),
        bot_token=os.environ.get("BOT_TOKEN", ""),
        owner_id=int(os.environ.get("OWNER_ID") or 0),
        reels_tools=Path(y["reels_tools"]),
        reels_pipeline=Path(y["reels_pipeline"]),
        claude_bin=y["claude_bin"],
        whisper_bin=y["whisper_bin"],
        whisper_model=y["whisper_model"],
        select_threshold=float(y["select_threshold"]),
        max_frames=int(y["max_frames"]),
        batch_size=int(y["batch_size"]),
        min_free_gb=float(y["min_free_gb"]),
        claude_timeout=int(y["claude_timeout"]),
        keywords=[k.lower() for k in y["keywords"]],
    )


def load_themes(root: Path) -> dict[str, Theme]:
    y = yaml.safe_load((root / "config" / "themes.yaml").read_text())
    return {n: Theme(n, v["folder"], v["moc"]) for n, v in y["themes"].items()}
```

`reels_radar/db.py`:
```python
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  code TEXT PRIMARY KEY, url TEXT NOT NULL, caption TEXT NOT NULL DEFAULT '',
  ts INTEGER NOT NULL DEFAULT 0, folder TEXT,
  status TEXT NOT NULL DEFAULT 'new', attempts INTEGER NOT NULL DEFAULT 0, fail_reason TEXT,
  ocr_text TEXT, transcript TEXT, score REAL,
  theme TEXT, purposes TEXT, kind TEXT, summary TEXT, template TEXT, title TEXT, body TEXT,
  note_path TEXT, note_created INTEGER, moc_line TEXT,
  updated TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS items_status ON items(status);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""

FIELDS = {"url", "caption", "ts", "folder", "status", "attempts", "fail_reason", "ocr_text", "transcript",
          "score", "theme", "purposes", "kind", "summary", "template", "title", "body", "note_path",
          "note_created", "moc_line"}


class DB:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(str(path))
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)

    def add_item(self, code, url, caption, ts, folder=None) -> bool:
        cur = self.c.execute(
            "INSERT OR IGNORE INTO items(code,url,caption,ts,folder,updated) VALUES(?,?,?,?,?,?)",
            (code, url, caption, ts, folder, datetime.now().isoformat()))
        self.c.commit()
        return cur.rowcount == 1

    def get(self, code):
        return self.c.execute("SELECT * FROM items WHERE code=?", (code,)).fetchone()

    def by_status(self, status, limit=100):
        return self.c.execute("SELECT * FROM items WHERE status=? ORDER BY ts DESC LIMIT ?",
                              (status, limit)).fetchall()

    def update(self, code, **fields):
        bad = set(fields) - FIELDS
        if bad:
            raise KeyError(f"unknown fields: {bad}")
        fields["updated"] = datetime.now().isoformat()
        sets = ",".join(f"{k}=?" for k in fields)
        self.c.execute(f"UPDATE items SET {sets} WHERE code=?", (*fields.values(), code))
        self.c.commit()

    def counts(self) -> dict[str, int]:
        return {r[0]: r[1] for r in self.c.execute("SELECT status, COUNT(*) FROM items GROUP BY status")}

    def kv_get(self, key, default=None):
        r = self.c.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
        return r[0] if r else default

    def kv_set(self, key, value):
        self.c.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                       (key, str(value)))
        self.c.commit()
```

- [ ] **Step 5: Run, expect PASS** — `uv run pytest -q`.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: scaffold, config, db"` (с трейлером).

---

### Task 2: Парсер экспорта

**Files:** Create `reels_radar/export.py`; Test `tests/test_export.py`

**Interfaces:**
- Produces: `fix(s) -> str` (латин1→utf8, при ошибке исходная строка), `shortcode(url) -> str | None`, `Parsed` dataclass `(code, url, caption, ts, folder)`, `parse_export(dir: Path) -> list[Parsed]` (по убыванию ts, без дублей кодов). Источники: `**/saved_posts.json`, `**/message_*.json` (поле `share.link`), а также `**/saved_collections*.json` если есть (поле папки пробуется по ключам `Название`/`name`/`title` коллекции и списку `saved_media`/`items`; форма не подтверждена, поэтому `folder` может остаться `None`).

- [ ] **Step 1: Failing test** `tests/test_export.py`:
```python
import json
from reels_radar.export import fix, shortcode, parse_export


def mojibake(s: str) -> str:
    return s.encode("utf8").decode("latin1")


def test_fix_roundtrip_and_plain():
    assert fix(mojibake("Описание")) == "Описание"
    assert fix("plain") == "plain"


def test_shortcode():
    assert shortcode("https://www.instagram.com/reel/AbC_1-x/?x=1") == "AbC_1-x"
    assert shortcode("https://example.com/") is None


def _saved(tmp_path, entries):
    (tmp_path / "saved_posts.json").write_text(json.dumps(entries))


def test_parse_saved_posts(tmp_path):
    _saved(tmp_path, [
        {"timestamp": 200, "media": [], "label_values": [
            {"label": "URL", "value": "https://www.instagram.com/reel/AAA/"},
            {"label": mojibake("Описание"), "value": mojibake("Как снимать")}]},
        {"timestamp": 100, "media": [], "label_values": [
            {"label": "URL", "value": "https://www.instagram.com/reel/BBB/"}]},
        {"timestamp": 50, "media": [], "label_values": [{"label": mojibake("Описание"), "value": "x"}]},
        {"timestamp": 10, "media": [], "label_values": [
            {"label": "URL", "value": "https://www.instagram.com/reel/AAA/"}]},
    ])
    items = parse_export(tmp_path)
    assert [i.code for i in items] == ["AAA", "BBB"]
    assert items[0].caption == "Как снимать" and items[1].caption == ""
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** `reels_radar/export.py`:
```python
from __future__ import annotations

import glob
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Parsed:
    code: str
    url: str
    caption: str
    ts: int
    folder: str | None = None


def fix(s) -> str:
    if not isinstance(s, str):
        return ""
    try:
        return s.encode("latin1").decode("utf8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def shortcode(url) -> str | None:
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else None


def _saved_posts(path) -> list[Parsed]:
    out = []
    for p in json.load(open(path)):
        url, cap = "", ""
        for lv in p.get("label_values", []):
            label = fix(lv.get("label", ""))
            if label == "URL":
                url = lv.get("value", "")
            elif label.startswith("Опис"):
                cap = fix(lv.get("value", ""))
        code = shortcode(url)
        if code:
            out.append(Parsed(code, url.split("?")[0], cap, int(p.get("timestamp", 0))))
    return out


def _messages(path) -> list[Parsed]:
    out = []
    for m in json.load(open(path)).get("messages", []):
        sh = m.get("share") or {}
        code = shortcode(sh.get("link"))
        if code:
            out.append(Parsed(code, sh["link"].split("?")[0], fix(sh.get("share_text")),
                              int(m.get("timestamp_ms", 0)) // 1000))
    return out


def parse_export(root: Path) -> list[Parsed]:
    found: dict[str, Parsed] = {}
    paths = [(p, _saved_posts) for p in glob.glob(str(Path(root) / "**" / "saved_posts.json"), recursive=True)]
    paths += [(p, _messages) for p in glob.glob(str(Path(root) / "**" / "message_*.json"), recursive=True)]
    for path, fn in paths:
        for it in fn(path):
            found.setdefault(it.code, it)
    return sorted(found.values(), key=lambda x: -x.ts)
```
Папки коллекций (`saved_collections*.json`) в Task 2 не парсятся: формат не подтверждён. Задача 11 (пилот) смотрит новый экспорт и добавляет разбор, если файл есть.

- [ ] **Step 4: Run, expect PASS.** **Step 5: Commit** `feat: export parser`.

---

### Task 3: Отсев повторов

**Files:** Create `reels_radar/dedup.py`; Test `tests/test_dedup.py`

**Interfaces:**
- Consumes: `Parsed`, `DB`.
- Produces: `known_codes(reels_pipeline: Path, reels_tools: Path, db: DB) -> set[str]`, `ingest(items: list[Parsed], known: set[str], db: DB) -> int` (добавляет только новые, возвращает число добавленных).

- [ ] **Step 1: Failing test:**
```python
import json
from reels_radar.dedup import known_codes, ingest
from reels_radar.export import Parsed


def test_known_codes_reads_all_sources(tmp_path, db):
    pipe, tools = tmp_path / "p", tmp_path / "t"
    pipe.mkdir(); tools.mkdir()
    (pipe / "items_by_key.json").write_text(json.dumps({"OLD1": {}, "OLD2": {}}))
    (tools / "results.jsonl").write_text(json.dumps({"code": "OLD3"}) + "\n" + "\n")
    db.add_item("DB1", "u", "", 1)
    assert known_codes(pipe, tools, db) == {"OLD1", "OLD2", "OLD3", "DB1"}


def test_missing_sources_ok(tmp_path, db):
    assert known_codes(tmp_path, tmp_path, db) == set()


def test_ingest_only_new(db):
    items = [Parsed("A", "u", "c", 1), Parsed("B", "u", "c", 2), Parsed("A", "u", "c", 3)]
    assert ingest(items, {"B"}, db) == 1
    assert db.get("A") is not None and db.get("B") is None
```
(Если структура `items_by_key.json` окажется списком, а не словарём: тест Step 1 исполнитель сверяет с реальным файлом `head -c 300` и подгоняет `known_codes` и тест вместе. Проверка обязательна.)

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement:**
```python
from __future__ import annotations

import json
from pathlib import Path

from .db import DB
from .export import Parsed


def _items_by_key(p: Path) -> set[str]:
    f = p / "items_by_key.json"
    if not f.exists():
        return set()
    d = json.load(open(f))
    return set(d.keys()) if isinstance(d, dict) else {x["code"] for x in d if isinstance(x, dict) and "code" in x}


def _results(p: Path) -> set[str]:
    f = p / "results.jsonl"
    out = set()
    if f.exists():
        for line in open(f):
            line = line.strip()
            if line:
                try:
                    out.add(json.loads(line)["code"])
                except (ValueError, KeyError):
                    pass
    return out


def known_codes(reels_pipeline: Path, reels_tools: Path, db: DB) -> set[str]:
    known = _items_by_key(Path(reels_pipeline)) | _results(Path(reels_tools))
    known |= {r[0] for r in db.c.execute("SELECT code FROM items")}
    return known


def ingest(items: list[Parsed], known: set[str], db: DB) -> int:
    n = 0
    for it in items:
        if it.code in known:
            continue
        if db.add_item(it.code, it.url, it.caption, it.ts, it.folder):
            known.add(it.code)
            n += 1
    return n
```
- [ ] **Step 4: Run, expect PASS.** **Step 5: Commit** `feat: dedup`.

---

### Task 4: Цепочка получения видео

**Files:** Create `reels_radar/fetch.py`, `scripts/pw_fetch.py`; Test `tests/test_fetch.py`

**Interfaces:**
- Produces: `FetchResult = (status, path)`, где `status in {"OK","LOGIN","RATE","NO_VIDEO"}`; `Fetcher = Callable[[str, Path], str]` (url, dest_dir) → status; `fetch_ytdlp(url, dest, cookies) -> str`, `fetch_playwright(url, dest, script) -> str`, `fetch_gallerydl(url, dest, cookies) -> str`, `fetch_chain(url, dest, fetchers: list[Fetcher]) -> tuple[str, Path | None]`. Цепочка: останавливается на первом `OK`; `RATE` прерывает цепочку (не долбим дальше); `LOGIN`/`NO_VIDEO` идут к следующему. Видеофайл ищется в `dest` по расширению `.mp4/.mov/.webm`.

- [ ] **Step 1: Failing test:**
```python
from pathlib import Path
from reels_radar.fetch import fetch_chain


def mk(status, make_file=False):
    def f(url, dest: Path):
        if make_file:
            (dest / "v.mp4").write_bytes(b"x")
        return status
    return f


def test_first_ok_wins(tmp_path):
    st, path = fetch_chain("u", tmp_path, [mk("LOGIN"), mk("OK", True), mk("OK", True)])
    assert st == "OK" and path.name == "v.mp4"


def test_rate_stops_chain(tmp_path):
    calls = []
    def spy(url, dest):
        calls.append(1); return "OK"
    st, path = fetch_chain("u", tmp_path, [mk("RATE"), spy])
    assert st == "RATE" and path is None and not calls


def test_all_fail_is_no_video(tmp_path):
    st, path = fetch_chain("u", tmp_path, [mk("LOGIN"), mk("NO_VIDEO")])
    assert st == "NO_VIDEO" and path is None


def test_ok_without_file_continues(tmp_path):
    st, path = fetch_chain("u", tmp_path, [mk("OK", False), mk("OK", True)])
    assert st == "OK" and path is not None
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** `reels_radar/fetch.py`:
```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

VID = {".mp4", ".mov", ".webm"}
Fetcher = Callable[[str, Path], str]


def _video(dest: Path) -> Path | None:
    return next((p for p in sorted(Path(dest).glob("*")) if p.suffix.lower() in VID), None)


def _classify(err: str) -> str | None:
    e = err.lower()
    if "login_required" in e or "redirect to login" in e or "log in" in e:
        return "LOGIN"
    if "429" in e or "rate limit" in e or "please wait a few minutes" in e or "redirect to home page" in e:
        return "RATE"
    return None


def fetch_ytdlp(url: str, dest: Path, cookies: Path) -> str:
    p = subprocess.run(["yt-dlp", "--cookies", str(cookies), "-o", str(dest / "%(id)s.%(ext)s"), url],
                       capture_output=True, text=True, timeout=300)
    return "OK" if p.returncode == 0 else (_classify(p.stderr + p.stdout) or "NO_VIDEO")


def fetch_gallerydl(url: str, dest: Path, cookies: Path) -> str:
    p = subprocess.run(["gallery-dl", "--cookies", str(cookies), "-D", str(dest), url],
                       capture_output=True, text=True, timeout=300)
    return "OK" if p.returncode == 0 else (_classify(p.stderr + p.stdout) or "NO_VIDEO")


def fetch_playwright(url: str, dest: Path, script: Path, profile: Path) -> str:
    p = subprocess.run([sys.executable, str(script), url, str(dest), str(profile)],
                       capture_output=True, text=True, timeout=300)
    return {0: "OK", 2: "LOGIN", 3: "RATE"}.get(p.returncode, "NO_VIDEO")


def fetch_chain(url: str, dest: Path, fetchers: list[Fetcher]) -> tuple[str, Path | None]:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    last = "NO_VIDEO"
    for f in fetchers:
        st = f(url, dest)
        if st == "RATE":
            return "RATE", None
        if st == "OK":
            v = _video(dest)
            if v:
                return "OK", v
            st = "NO_VIDEO"
        last = st
    return ("LOGIN" if last == "LOGIN" else "NO_VIDEO"), None
```
Порядок в проде (Task 8): `[ytdlp, playwright, gallerydl]` с готовыми через `functools.partial`.

`scripts/pw_fetch.py` (запускается интерпретатором, где стоит playwright; `uv add playwright && uv run playwright install chromium` делается в Step 4):
```python
"""pw_fetch.py URL DEST PROFILE: открыть рилс в залогиненном профиле и перехватить URL медиа.
Коды выхода: 0 готово, 2 нужен логин, 3 лимит, 1 не вышло. Не печатает cookie."""
import sys, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

url, dest, profile = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
media = []
with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(profile, headless=True)
    page = ctx.new_page()
    page.on("response", lambda r: media.append(r.url) if "video" in r.headers.get("content-type", "") else None)
    page.goto(url, wait_until="networkidle", timeout=60000)
    if "/accounts/login" in page.url:
        sys.exit(2)
    page.wait_for_timeout(3000)
    ctx.close()
if not media:
    sys.exit(1)
src = media[-1].split("&bytestart")[0]
req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
(dest / "pw.mp4").write_bytes(urllib.request.urlopen(req, timeout=120).read())
sys.exit(0)
```
- [ ] **Step 4: Run tests, expect PASS** (цепочка на подменах). Добавить зависимость: `uv add playwright && uv run playwright install chromium`. Живая проверка `pw_fetch.py` и выбор логина в профиле `data/pw-profile` вручную с Некитом в Task 11, не в тестах.
- [ ] **Step 5: Commit** `feat: video fetch chain`.

---

### Task 5: Локальный разбор и скоринг

**Files:** Create `reels_radar/local.py`; Test `tests/test_local.py`

**Interfaces:**
- Consumes: `Settings`.
- Produces: `clean_lines(blocks: list[str]) -> list[str]`, `score(transcript: str, ocr_text: str, caption: str, keywords: list[str]) -> float`, `extract_frames(video: Path, out: Path, n: int) -> list[Path]` (равномерно, jpg ≤720 px), `run_ocr(ocr_bin: Path, paths) -> list[str]`, `transcribe(whisper_bin, model, video) -> str`, `analyze_local(s, video, workdir) -> LocalResult(transcript, ocr_text, score, frames)`. Кадры остаются в `workdir/frames` до явного удаления вызывающим.

- [ ] **Step 1: Failing test (чистая логика):**
```python
from reels_radar.local import clean_lines, score


def test_clean_lines_dedups_and_drops_noise():
    blocks = ["Hello world\n12:30\nab", "hello   WORLD\nПривет мир"]
    assert clean_lines(blocks) == ["Hello world", "Привет мир"]


def test_score_monotonic_and_capped():
    kw = ["claude"]
    low = score("", "", "", kw)
    mid = score("слово " * 100, "", "", kw)
    assert low == 0 and mid > low
    assert score("слово " * 10000, "текст " * 10000, "claude " * 50, kw) <= 100


def test_keywords_add_points():
    assert score("", "", "claude mcp", ["claude", "mcp"]) > score("", "", "ничего", ["claude", "mcp"])
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement:**
```python
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


@dataclass
class LocalResult:
    transcript: str
    ocr_text: str
    score: float
    frames: list[Path]


def clean_lines(blocks: list[str]) -> list[str]:
    seen, out = set(), []
    for blk in blocks:
        for ln in blk.splitlines():
            ln = ln.strip()
            key = re.sub(r"[^\wа-яё]+", "", ln.lower())
            if len(key) < 3 or re.fullmatch(r"[\d:.,]+", ln) or key in seen:
                continue
            seen.add(key)
            out.append(ln)
    return out


def score(transcript: str, ocr_text: str, caption: str, keywords: list[str]) -> float:
    s = min(len(transcript) / 20, 50) + min(len(ocr_text) / 20, 25)
    hay = f"{transcript} {ocr_text} {caption}".lower()
    s += min(sum(1 for k in keywords if k in hay) * 5, 25)
    return round(min(s, 100.0), 1)


def extract_frames(video: Path, out: Path, n: int) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, timeout=60).stdout.strip() or 0)
    step = max(dur / (n + 1), 0.5)
    for i in range(n):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(step * (i + 1)), "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=720:-1", str(out / f"f{i:02d}.jpg")], timeout=60)
    return sorted(out.glob("f*.jpg"))


def run_ocr(ocr_bin: Path, paths: list[Path]) -> list[str]:
    if not paths:
        return []
    r = subprocess.run([str(ocr_bin), *map(str, paths)], capture_output=True, text=True, timeout=600)
    return [b.strip() for b in r.stdout.split("=====")]


def transcribe(whisper_bin: str, model: str, video: Path, tmp: Path) -> str:
    tmp.mkdir(parents=True, exist_ok=True)
    subprocess.run([whisper_bin, str(video), "--model", model, "--output-format", "txt",
                    "--output-dir", str(tmp), "--verbose", "False", "--condition-on-previous-text", "False"],
                   capture_output=True, text=True, timeout=900)
    f = tmp / (video.stem + ".txt")
    text = f.read_text().strip() if f.exists() else ""
    return text if len(text) >= 15 else ""


def analyze_local(s: Settings, video: Path, workdir: Path, caption: str = "") -> LocalResult:
    frames = extract_frames(video, workdir / "frames", s.max_frames)
    ocr_text = " / ".join(clean_lines(run_ocr(s.reels_tools / "ocr", frames)))
    transcript = transcribe(s.whisper_bin, s.whisper_model, video, workdir / "stt")
    return LocalResult(transcript, ocr_text, score(transcript, ocr_text, caption, s.keywords), frames)
```
- [ ] **Step 4: Run, expect PASS** (проверяются только чистые функции). Живую проверку `analyze_local` на одном видео выполнить в Task 11.
- [ ] **Step 5: Commit** `feat: local analysis and score`.

---

### Task 6: Анализ кадров через claude -p

**Files:** Create `reels_radar/claude.py`, `reels_radar/vision.py`; Test `tests/test_vision.py`

**Interfaces:**
- Consumes: `Settings`, `Theme`.
- Produces: `run_claude(s, prompt, *, system, schema, tools=(), add_dirs=(), timeout) -> dict` (копия `tg-harvester/harvester/brain.py:54`, исключения `BrainError`, `is_limit(e)`); `PURPOSES = ("note","content","product","claude","friend")`, `KINDS = ("знание","приём","идея","фича")`; `SCHEMA`; `build_prompt(code, caption, transcript, ocr_text, frames, themes, folder_theme) -> str`; `Verdict` dataclass `(theme, purposes: list[str], kind, summary, template, title, body, skip, reason)`; `validate(raw: dict, themes: dict) -> Verdict` (нормализация: неизвестная тема → `Разное`; пустые purposes → `["note"]`; удаление длинного тире; `skip` при `skip=true`); `async classify(s, themes, item, local, claude=run_claude) -> Verdict`.

- [ ] **Step 1: Failing test:**
```python
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
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** `reels_radar/claude.py`: скопировать `run_claude`, `BrainError`, `is_limit` из `tg-harvester/harvester/brain.py:17-60,116-120` без изменений логики, заменив `s.data_dir` на `s.data_dir` (поле есть в `Settings`) и импорты `.config`. Затем `reels_radar/vision.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field

from .claude import run_claude
from .config import Theme

PURPOSES = ("note", "content", "product", "claude", "friend")
KINDS = ("знание", "приём", "идея", "фича")

SYSTEM = """Ты разбираешь сохранённый рилс Некита для его Obsidian и контента. Отвечай по-русски, строго по JSON-схеме.
Оценивай по кадрам (файлы изображений можно открыть инструментом Read) и расшифровке, не только по подписи.
purposes, можно несколько: note (знание или приём в заметку), content (идея и шаблон для его рилсов и тредов), product (идея фичи продукта), claude (улучшение работы Claude: скилл, фича, промпт, сетап), friend (переслать другу, в заметки не пишется).
Тема строго из списка. title: содержательное название заметки до 80 символов, без авторов и каналов. body: суть markdown без заголовка верхнего уровня, промпты и команды дословно в блоке кода.
Для content заполни template: хук, структура по секундам, длительность, звук, что снимать. Для темы «Слова и фразы» body = фраза, смысл, где уместна.
skip=true с reason, если рилс пустой, реклама, воронка без сути. Не выдумывай то, чего нет в материале. Без длинного тире, имён авторов и юзернеймов."""

SCHEMA = {
    "type": "object",
    "properties": {
        "theme": {"type": "string"}, "purposes": {"type": "array", "items": {"type": "string"}},
        "kind": {"type": "string"}, "summary": {"type": "string"}, "template": {"type": "string"},
        "title": {"type": "string"}, "body": {"type": "string"}, "skip": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["theme", "purposes", "kind", "summary", "template", "title", "body", "skip", "reason"],
}


@dataclass
class Verdict:
    theme: str
    purposes: list[str]
    kind: str
    summary: str
    template: str
    title: str
    body: str
    skip: bool = False
    reason: str = ""


def _clean(s: str) -> str:
    return (s or "").replace("—", "-").strip()


def validate(raw: dict, themes: dict[str, Theme]) -> Verdict:
    theme = raw.get("theme") if raw.get("theme") in themes else "Разное"
    purposes = [p for p in raw.get("purposes", []) if p in PURPOSES] or ["note"]
    kind = raw.get("kind") if raw.get("kind") in KINDS else "знание"
    return Verdict(theme, purposes, kind, _clean(raw.get("summary")), _clean(raw.get("template")),
                   _clean(raw.get("title"))[:80], _clean(raw.get("body")), bool(raw.get("skip")),
                   _clean(raw.get("reason")))


def build_prompt(code, caption, transcript, ocr_text, frames, themes, folder_theme) -> str:
    parts = [f"Темы: {', '.join(themes)}."]
    if folder_theme:
        parts.append(f"Папка Instagram задаёт тему: {folder_theme}.")
    parts += [f"Подпись: {caption}", f"Расшифровка речи: {transcript}", f"Текст на экране (OCR): {ocr_text}"]
    if frames:
        parts.append("Кадры (открой через Read): " + ", ".join(str(f) for f in frames))
    return "\n".join(parts)


async def classify(s, themes, item, local, claude=run_claude, folder_theme=None) -> Verdict:
    prompt = build_prompt(item.code, item.caption, local.transcript, local.ocr_text, local.frames,
                          themes, folder_theme)
    dirs = tuple({str(f.parent) for f in local.frames})
    raw = await claude(s, prompt, system=SYSTEM, schema=SCHEMA, tools=("Read",) if local.frames else (),
                       add_dirs=dirs, timeout=s.claude_timeout)
    return validate(raw, themes)
```
- [ ] **Step 4: Run, expect PASS.** **Step 5: Commit** `feat: vision classify via claude -p`.

---

### Task 7: Карточки, ревью, запись в vault

**Files:** Create `reels_radar/cards.py`, `reels_radar/review.py`, `reels_radar/vault.py`; Test `tests/test_cards.py`, `tests/test_review.py`, `tests/test_vault.py`

**Interfaces:**
- Consumes: `DB`, `Theme`, `Verdict`.
- Produces:
  - `cards.render_card(row) -> str`; `cards.keyboard_spec(code) -> list[list[tuple[str,str]]]` (кнопки `ok:<code>`, `no:<code>`, `edit:<code>`, `theme:<code>`); `cards.parse_callback(data) -> tuple[str,str]`; `cards.THEME_PICK` не нужен (тема меняется ответным списком из `themes`).
  - `review.save_verdict(db, code, v: Verdict)` пишет поля и статус `draft` (или `archived` при `skip`); `review.apply_action(db, code, action, themes, vault) -> str` для `ok|no|set_theme:<name>|set_purposes:<csv>`; при `ok` и purposes без `note` (то есть только `friend`/`content`/`product`/`claude`) заметка пишется только если в purposes есть `note`, `product` или `claude`; `friend` и `content` остаются в БД (статус `approved`).
  - `vault.write_note(vault: Path, theme: Theme, title, body, code) -> tuple[Path, bool]` (создаёт новую заметку `folder/<safe title>.md`, не перезаписывает существующую: при дубле добавляет суффикс ` (2)`); `vault.add_moc_line(vault, theme, title) -> str`; `vault.rollback(vault, db, code) -> str` (перенос файла в `.trash/` с сохранением пути, удаление строки из MOC).
  - `safe_title(title) -> str` убирает `/\:*?"<>|`, схлопывает пробелы, максимум 80 символов.

- [ ] **Step 1: Failing tests:**

`tests/test_vault.py`:
```python
from reels_radar.config import Theme
from reels_radar.vault import safe_title, write_note, add_moc_line

T = Theme("ИИ", "ИИ работа", "ИИ работа — карта заметок.md")


def test_safe_title():
    assert safe_title('A/B: "тест"?') == "AB тест"
    assert len(safe_title("x" * 200)) == 80


def test_write_note_never_overwrites(tmp_path):
    p1, c1 = write_note(tmp_path, T, "Заголовок", "тело", "AAA")
    p2, c2 = write_note(tmp_path, T, "Заголовок", "другое", "BBB")
    assert p1 != p2 and c1 and c2
    assert p1.read_text().startswith("тело") or "тело" in p1.read_text()
    assert p2.parent == tmp_path / "ИИ работа"


def test_moc_line_appended_once(tmp_path):
    (tmp_path / "ИИ работа").mkdir()
    moc = tmp_path / "ИИ работа" / T.moc
    moc.write_text("# MOC\n")
    add_moc_line(tmp_path, T, "Заголовок")
    add_moc_line(tmp_path, T, "Заголовок")
    assert moc.read_text().count("[[Заголовок]]") == 1
```
`tests/test_review.py`:
```python
from reels_radar.config import Theme
from reels_radar.review import save_verdict, apply_action
from reels_radar.vision import Verdict

THEMES = {"ИИ": Theme("ИИ", "ИИ работа", "m.md"), "Разное": Theme("Разное", "Разное", "r.md")}


def v(purposes, skip=False):
    return Verdict("ИИ", purposes, "знание", "суть", "", "Заг", "тело", skip, "")


def test_skip_goes_to_archive(db):
    db.add_item("A", "u", "", 1)
    save_verdict(db, "A", v(["note"], skip=True))
    assert db.get("A")["status"] == "archived"


def test_ok_note_writes_file(db, tmp_path):
    db.add_item("A", "u", "", 1)
    save_verdict(db, "A", v(["note"]))
    apply_action(db, "A", "ok", THEMES, tmp_path)
    r = db.get("A")
    assert r["status"] == "written" and (tmp_path / r["note_path"]).exists()


def test_ok_friend_only_writes_nothing(db, tmp_path):
    db.add_item("A", "u", "", 1)
    save_verdict(db, "A", v(["friend"]))
    apply_action(db, "A", "ok", THEMES, tmp_path)
    assert db.get("A")["status"] == "approved" and not list(tmp_path.iterdir())


def test_no_rejects_and_theme_change(db, tmp_path):
    db.add_item("A", "u", "", 1)
    save_verdict(db, "A", v(["note"]))
    apply_action(db, "A", "set_theme:Разное", THEMES, tmp_path)
    assert db.get("A")["theme"] == "Разное"
    apply_action(db, "A", "no", THEMES, tmp_path)
    assert db.get("A")["status"] == "rejected"
```
`tests/test_cards.py`:
```python
from reels_radar.cards import render_card, keyboard_spec, parse_callback


def test_callback_roundtrip():
    for label, data in keyboard_spec("AAA")[0]:
        assert parse_callback(data)[1] == "AAA"


def test_card_has_no_long_dash(db):
    db.add_item("A", "https://i/reel/A/", "", 1)
    db.update("A", theme="ИИ", purposes="claude,note", kind="фича", summary="суть", template="шаблон")
    text = render_card(db.get("A"))
    assert "—" not in text and "ИИ" in text and "суть" in text
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**

`reels_radar/vault.py`:
```python
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import Theme


def safe_title(title: str) -> str:
    t = re.sub(r'[\\/:*?"<>|]', "", title)
    return re.sub(r"\s+", " ", t).strip()[:80] or "Без названия"


def write_note(vault: Path, theme: Theme, title: str, body: str, code: str) -> tuple[Path, bool]:
    folder = Path(vault) / theme.folder
    folder.mkdir(parents=True, exist_ok=True)
    base = safe_title(title)
    path, n = folder / f"{base}.md", 2
    while path.exists():
        path = folder / f"{base} ({n}).md"
        n += 1
    assert path.resolve().is_relative_to(folder.resolve())
    path.write_text(body.rstrip() + "\n", encoding="utf8")
    return path, True


def add_moc_line(vault: Path, theme: Theme, title: str) -> str:
    moc = Path(vault) / theme.folder / theme.moc
    line = f"- [[{safe_title(title)}]]"
    text = moc.read_text(encoding="utf8") if moc.exists() else ""
    if line not in text:
        moc.parent.mkdir(parents=True, exist_ok=True)
        moc.write_text(text.rstrip("\n") + "\n" + line + "\n", encoding="utf8")
    return line


def rollback(vault: Path, db, code: str, themes: dict[str, Theme]) -> str:
    r = db.get(code)
    if not r or not r["note_path"]:
        return "нечего откатывать"
    src = Path(vault) / r["note_path"]
    if src.exists():
        dst = Path(vault) / ".trash" / r["note_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    theme = themes.get(r["theme"])
    if theme and r["moc_line"]:
        moc = Path(vault) / theme.folder / theme.moc
        if moc.exists():
            moc.write_text(moc.read_text(encoding="utf8").replace(r["moc_line"] + "\n", ""), encoding="utf8")
    db.update(code, status="draft", note_path=None, note_created=None, moc_line=None)
    return "заметка перенесена в .trash"
```
`reels_radar/review.py`:
```python
from __future__ import annotations

from pathlib import Path

from .vault import add_moc_line, write_note

WRITES = {"note", "product", "claude"}


def save_verdict(db, code, v) -> None:
    db.update(code, status="archived" if v.skip else "draft", fail_reason=v.reason or None,
              theme=v.theme, purposes=",".join(v.purposes), kind=v.kind, summary=v.summary,
              template=v.template, title=v.title, body=v.body)


def apply_action(db, code, action, themes, vault: Path) -> str:
    r = db.get(code)
    if action == "no":
        db.update(code, status="rejected")
        return "отклонено"
    if action.startswith("set_theme:"):
        name = action.split(":", 1)[1]
        if name in themes:
            db.update(code, theme=name)
        return f"тема: {name}"
    if action.startswith("set_purposes:"):
        db.update(code, purposes=action.split(":", 1)[1])
        return "цели обновлены"
    if action == "ok":
        purposes = set((r["purposes"] or "").split(","))
        if not purposes & WRITES:
            db.update(code, status="approved")
            return "сохранено в базе"
        theme = themes[r["theme"]]
        path, created = write_note(vault, theme, r["title"], r["body"], code)
        line = add_moc_line(vault, theme, r["title"])
        db.update(code, status="written", note_path=str(path.relative_to(vault)),
                  note_created=int(created), moc_line=line)
        return f"записано: {path.name}"
    raise ValueError(f"unknown action {action}")
```
`reels_radar/cards.py`:
```python
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
```
- [ ] **Step 4: Run, expect PASS.** **Step 5: Commit** `feat: cards, review, vault writer with rollback`.

---

### Task 8: Конвейер

**Files:** Create `reels_radar/pipeline.py`; Test `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 1-7.
- Produces: `async run_batch(s, db, themes, *, fetch, local, classify, limit=None) -> dict[str,int]` где `fetch(item_row, workdir) -> (status, path|None)`, `local(video, workdir, caption) -> LocalResult`, `classify(item_row, local_result) -> Verdict` (все внедряются; в проде оборачивают Task 4-6). Логика на каждую `new`/`no_video` запись (с `attempts < 3`): fetch → `LOGIN/RATE`: стоп RATE (пауза очереди, `kv paused=1`), LOGIN → `no_video`; `NO_VIDEO` → статус `no_video`, `attempts+1`; `OK` → local → записать transcript/ocr/score → если `score < threshold` и есть расшифровка или OCR → `archived`; если видео есть, но речи и текста нет, а score низкий → `archived`; иначе classify → `save_verdict`. Лимит `claude`: исключение с `is_limit` → `kv paused=1`, запись остаётся `local`, цикл выходит. Кадры и видео всегда удаляются в `finally`.

- [ ] **Step 1: Failing test:**
```python
import asyncio
from pathlib import Path
from reels_radar.config import Theme
from reels_radar.local import LocalResult
from reels_radar.pipeline import run_batch
from reels_radar.vision import Verdict

THEMES = {"ИИ": Theme("ИИ", "f", "m"), "Разное": Theme("Разное", "f", "m")}


class S:
    select_threshold = 30
    data_dir = None


def mk_local(score):
    return lambda video, workdir, caption: LocalResult("речь", "ocr", score, [])


async def ok_classify(row, lr):
    return Verdict("ИИ", ["note"], "знание", "с", "", "Т", "тело")


def ok_fetch(row, workdir):
    p = Path(workdir) / "v.mp4"; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b"x")
    return "OK", p


def run(db, tmp_path, **kw):
    s = S(); s.data_dir = tmp_path
    return asyncio.run(run_batch(s, db, THEMES, **kw))


def test_high_score_becomes_draft(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    run(db, tmp_path, fetch=ok_fetch, local=mk_local(80), classify=ok_classify)
    assert db.get("A")["status"] == "draft" and not (tmp_path / "work" / "A").exists()


def test_low_score_archived_without_claude(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    async def boom(row, lr): raise AssertionError("claude must not be called")
    run(db, tmp_path, fetch=ok_fetch, local=mk_local(5), classify=boom)
    assert db.get("A")["status"] == "archived"


def test_no_video_stays_in_queue(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    run(db, tmp_path, fetch=lambda r, w: ("NO_VIDEO", None), local=mk_local(80), classify=ok_classify)
    r = db.get("A")
    assert r["status"] == "no_video" and r["attempts"] == 1


def test_rate_pauses_queue(db, tmp_path):
    db.add_item("A", "u", "c", 1); db.add_item("B", "u", "c", 2)
    run(db, tmp_path, fetch=lambda r, w: ("RATE", None), local=mk_local(80), classify=ok_classify)
    assert db.kv_get("paused") == "1" and db.get("A")["status"] == "new" and db.get("B")["status"] == "new"


def test_claude_limit_pauses_keeps_local(db, tmp_path):
    db.add_item("A", "u", "c", 1)
    async def limit(row, lr): raise RuntimeError("usage limit reached")
    run(db, tmp_path, fetch=ok_fetch, local=mk_local(80), classify=limit)
    assert db.kv_get("paused") == "1" and db.get("A")["status"] == "local"
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement:**
```python
from __future__ import annotations

import shutil
from pathlib import Path

from .claude import is_limit
from .review import save_verdict


async def run_batch(s, db, themes, *, fetch, local, classify, limit=None) -> dict[str, int]:
    rows = [*db.by_status("new", limit or 1000), *db.by_status("no_video", limit or 1000)]
    rows = [r for r in rows if r["attempts"] < 3][: limit or None]
    stats = {"draft": 0, "archived": 0, "no_video": 0, "paused": 0}
    for r in rows:
        code = r["code"]
        work = Path(s.data_dir) / "work" / code
        try:
            status, video = fetch(r, work)
            if status == "RATE":
                db.kv_set("paused", "1"); stats["paused"] = 1
                break
            if status != "OK":
                db.update(code, status="no_video", attempts=r["attempts"] + 1, fail_reason=status)
                stats["no_video"] += 1
                continue
            lr = local(video, work, r["caption"])
            db.update(code, status="local", transcript=lr.transcript, ocr_text=lr.ocr_text, score=lr.score)
            if lr.score < s.select_threshold:
                db.update(code, status="archived"); stats["archived"] += 1
                continue
            try:
                v = await classify(db.get(code), lr)
            except Exception as e:
                if is_limit(e):
                    db.kv_set("paused", "1"); stats["paused"] = 1
                    break
                db.update(code, status="failed", attempts=r["attempts"] + 1, fail_reason=str(e)[:200])
                continue
            save_verdict(db, code, v)
            stats["archived" if v.skip else "draft"] += 1
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return stats
```
`is_limit` в `claude.py` (скопирован из харвестера) должен ловить строки `usage limit`, `rate limit`, `limit reached`; тест выше использует `RuntimeError("usage limit reached")`. Сверить с оригиналом (`brain.py:116`) и при расхождении поправить `is_limit`, не тест.
- [ ] **Step 4: Run, expect PASS.** **Step 5: Commit** `feat: pipeline batch`.

---

### Task 9: Дайджест

**Files:** Create `reels_radar/digest.py`; Test `tests/test_digest.py`

**Interfaces:** `build_digest(db, since_iso: str) -> str` (без длинного тире, без авторов): блоки «Для контента» (top-5 `purposes` содержит `content`, статус `draft|approved|written`, по `score`), «Фичи и приёмы Claude» (`purposes` содержит `claude`), «Слова и фразы» (тема `Слова и фразы`, до 5), «Нужен файл» (статус `no_video`, `attempts>=1`, ссылки), счётчики по статусам. Пустой блок не выводится.

- [ ] **Step 1: Failing test:**
```python
from reels_radar.digest import build_digest


def add(db, code, status, purposes, theme, score, summary="суть", template=""):
    db.add_item(code, f"https://i/reel/{code}/", "", 1)
    db.update(code, status=status, purposes=purposes, theme=theme, score=score, summary=summary,
              template=template, title=code)


def test_digest_blocks(db):
    add(db, "A", "draft", "content", "Съёмка и монтаж", 90, "хук 3 сек", "шаблон А")
    add(db, "B", "draft", "claude,note", "ИИ", 70)
    add(db, "C", "draft", "note", "Слова и фразы", 50, "фраза")
    db.add_item("D", "https://i/reel/D/", "", 1); db.update("D", status="no_video", attempts=1)
    text = build_digest(db, "2000-01-01")
    assert "шаблон А" in text and "Нужен файл" in text and "https://i/reel/D/" in text and "—" not in text


def test_empty_blocks_omitted(db):
    assert "Нужен файл" not in build_digest(db, "2000-01-01")
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement:**
```python
from __future__ import annotations

OK = ("draft", "approved", "written")


def _top(db, where, args, n):
    return db.c.execute(f"SELECT * FROM items WHERE status IN ('draft','approved','written') AND {where} "
                        f"AND updated >= ? ORDER BY score DESC LIMIT ?", (*args, n)).fetchall()


def build_digest(db, since_iso: str) -> str:
    out = ["Недельный дайджест"]
    content = _top(db, "purposes LIKE ?", ("%content%", since_iso), 5)
    if content:
        out += ["", "Для контента:"] + [f"- {r['summary']}\n  {r['template']}\n  {r['url']}" for r in content]
    claude = _top(db, "purposes LIKE ?", ("%claude%", since_iso), 5)
    if claude:
        out += ["", "Фичи и приёмы Claude:"] + [f"- {r['summary']}\n  {r['url']}" for r in claude]
    words = _top(db, "theme = ?", ("Слова и фразы", since_iso), 5)
    if words:
        out += ["", "Слова и фразы:"] + [f"- {r['summary']}" for r in words]
    need = db.c.execute("SELECT url FROM items WHERE status='no_video' AND attempts>=1 LIMIT 20").fetchall()
    if need:
        out += ["", "Нужен файл (видео не скачалось):"] + [f"- {r['url']}" for r in need]
    out += ["", "Счётчики: " + ", ".join(f"{k} {v}" for k, v in sorted(db.counts().items()))]
    return "\n".join(out).replace("—", "-")
```
Условие `updated >= since` использует то, что `updated` хранится ISO-строкой, сравнение лексикографическое работает.
- [ ] **Step 4: Run, expect PASS.** **Step 5: Commit** `feat: weekly digest`.

---

### Task 10: Бот и CLI

**Files:** Create `reels_radar/bot.py`, `reels_radar/cli.py`, `reels_radar/__main__.py`; Test `tests/test_cli.py`

**Interfaces:**
- Produces: `cli.main(argv) -> int` с командами `ingest <export_dir>` (парсит, отсекает повторы, пишет число новых), `run [--limit N]` (боевая сборка fetch/local/classify и `run_batch`), `digest [--days 7]` (печатает текст), `bot` (запускает aiogram polling). `bot.send_pending(bot, db, owner_id)` шлёт по одной карточке `draft`, помечает `kv sent:<code>`; обработчик callback вызывает `review.apply_action`, откат `/rollback <code>`, `/friends` показывает карточки с purposes=friend, `/status` счётчики, присланный владельцем видеофайл при `no_video` расшифровывается и переводит запись в обычный поток (см. Step 3 ниже). Все хендлеры проверяют `from_user.id == owner_id`.

- [ ] **Step 1: Failing test (только CLI ingest, остальное проверяется вживую в Task 11):**
```python
import json
from reels_radar.cli import main


def test_ingest_counts_new(tmp_path, monkeypatch):
    exp = tmp_path / "exp"; exp.mkdir()
    (exp / "saved_posts.json").write_text(json.dumps([
        {"timestamp": 1, "media": [], "label_values": [{"label": "URL", "value": "https://www.instagram.com/reel/NEW1/"}]}]))
    monkeypatch.setenv("REELS_RADAR_ROOT", str(tmp_path))
    (tmp_path / "config").mkdir()
    for n in ("settings.yaml", "themes.yaml"):
        (tmp_path / "config" / n).write_text(open(f"config/{n}").read())
    assert main(["ingest", str(exp)]) == 0
    from reels_radar.db import DB
    assert DB(tmp_path / "data" / "radar.db").get("NEW1") is not None
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** `cli.py` (корень проекта = `REELS_RADAR_ROOT` или родитель пакета; БД `data/radar.db`):
```python
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

from .config import load_settings, load_themes
from .db import DB
from .dedup import ingest, known_codes
from .digest import build_digest
from .export import parse_export


def root() -> Path:
    return Path(os.environ.get("REELS_RADAR_ROOT") or Path(__file__).resolve().parent.parent)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reels-radar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest"); p.add_argument("export_dir")
    p = sub.add_parser("run"); p.add_argument("--limit", type=int)
    p = sub.add_parser("digest"); p.add_argument("--days", type=int, default=7)
    sub.add_parser("bot")
    a = ap.parse_args(argv)
    r = root()
    s, themes = load_settings(r), load_themes(r)
    db = DB(s.data_dir / "radar.db")
    if a.cmd == "ingest":
        n = ingest(parse_export(Path(a.export_dir)), known_codes(s.reels_pipeline, s.reels_tools, db), db)
        print(f"новых: {n}")
    elif a.cmd == "digest":
        print(build_digest(db, (datetime.now() - timedelta(days=a.days)).isoformat()))
    elif a.cmd == "run":
        from .live import run_live
        print(asyncio.run(run_live(s, db, themes, a.limit)))
    elif a.cmd == "bot":
        from .bot import run_bot
        asyncio.run(run_bot(s, db, themes))
    return 0
```
`reels_radar/__main__.py`: `import sys; from .cli import main; sys.exit(main())`.

`reels_radar/live.py` (боевая сборка, тестами не покрывается, проверяется в Task 11):
```python
from __future__ import annotations

import shutil
from functools import partial
from pathlib import Path

from .fetch import fetch_chain, fetch_gallerydl, fetch_playwright, fetch_ytdlp
from .local import analyze_local
from .pipeline import run_batch
from .vision import classify


async def run_live(s, db, themes, limit=None):
    if shutil.disk_usage(Path.home()).free / 1e9 < s.min_free_gb:
        return {"error": "мало места на диске"}
    cookies = s.reels_tools / "ig_cookies.txt"
    pw = (s.root / "scripts" / "pw_fetch.py", s.data_dir / "pw-profile")
    chain = [partial(fetch_ytdlp, cookies=cookies),
             lambda u, d: fetch_playwright(u, d, *pw),
             partial(fetch_gallerydl, cookies=cookies)]

    def fetch(row, work):
        return fetch_chain(row["url"], work, chain)

    def local(video, work, caption):
        return analyze_local(s, video, work, caption)

    class It:
        pass

    async def cls(row, lr):
        it = It(); it.code, it.caption = row["code"], row["caption"]
        return await classify(s, themes, it, lr, folder_theme=row["folder"])

    return await run_batch(s, db, themes, fetch=fetch, local=local, classify=cls, limit=limit)
```
`reels_radar/bot.py` (aiogram 3, тонкий слой):
```python
from __future__ import annotations

from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .cards import keyboard_spec, parse_callback, render_card
from .review import apply_action
from .vault import rollback


def kb(code):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
                                                 for row in keyboard_spec(code)])


async def send_pending(bot: Bot, db, owner_id: int, limit: int = 10) -> int:
    n = 0
    for r in db.by_status("draft", 200):
        if db.kv_get(f"sent:{r['code']}"):
            continue
        await bot.send_message(owner_id, render_card(r), reply_markup=kb(r["code"]))
        db.kv_set(f"sent:{r['code']}", "1")
        n += 1
        if n >= limit:
            break
    return n


def router(s, db, themes) -> Router:
    rt = Router()
    owner = F.from_user.id == s.owner_id

    @rt.callback_query(owner)
    async def cb(q: CallbackQuery):
        action, code = parse_callback(q.data)
        if action == "theme":
            rows = [[InlineKeyboardButton(text=n, callback_data=f"st:{n}|{code}")] for n in themes]
            await q.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        elif action == "st":
            name, code = code.split("|", 1)
            apply_action(db, code, f"set_theme:{name}", themes, s.vault)
            await q.message.edit_text(render_card(db.get(code)), reply_markup=kb(code))
        elif action in ("ok", "no"):
            msg = apply_action(db, code, action, themes, s.vault)
            await q.message.edit_reply_markup(reply_markup=None)
            await q.answer(msg)
            return
        await q.answer()

    @rt.message(Command("status"), owner)
    async def status(m: Message):
        await m.answer(", ".join(f"{k} {v}" for k, v in sorted(db.counts().items())) or "пусто")

    @rt.message(Command("friends"), owner)
    async def friends(m: Message):
        rows = db.c.execute("SELECT summary,url FROM items WHERE purposes LIKE '%friend%' LIMIT 30").fetchall()
        await m.answer("\n\n".join(f"{r['summary']}\n{r['url']}" for r in rows) or "пусто")

    @rt.message(Command("rollback"), owner)
    async def rb(m: Message):
        code = (m.text or "").split(maxsplit=1)[-1].strip()
        await m.answer(rollback(s.vault, db, code, themes))

    return rt


async def run_bot(s, db, themes):
    bot = Bot(s.bot_token)
    dp = Dispatcher()
    dp.include_router(router(s, db, themes))
    await send_pending(bot, db, s.owner_id)
    await dp.start_polling(bot)
```
Приём видеофайла от владельца для `no_video` (расшифровать и вернуть в поток): отдельный мини-хендлер `F.video & owner` в `router`: сохраняет файл в `data/work/<code>/`, вызывает `analyze_local`, переводит запись в `new` с подготовленными полями; код хендлера пишет исполнитель по образцу `run_live.local`, привязка к `code` берётся из подписи к видео (`/file <code>`). Если по ходу реализации это разрастается за ~40 строк, вынести в Task 10b, не раздувая этот.
- [ ] **Step 4: Run, expect PASS** (`ingest`). Импорт-проверка: `uv run python -c "import reels_radar.bot, reels_radar.live"`.
- [ ] **Step 5: Commit** `feat: cli, live runner, bot`.

---

### Task 11: Живой пилот с Некитом

Не TDD, ручной чек-лист. Каждый шаг отмечается результатом в `HANDOFF.md` проекта.

- [ ] **Step 1: Бот.** Создать бота у @BotFather через telegram-mcp (имя `Reels Radar`), токен и `OWNER_ID` в `.env` (chmod 600), пароль 2FA вводит Некит.
- [ ] **Step 2: Темы.** Сверить `config/themes.yaml` с реальными папками и MOC в vault (`ls ~/Documents/Obsidian storage`), поправить `folder` и `moc`. Новые темы «Съёмка и монтаж» и «Слова и фразы» создать папкой и MOC (по `Правила оформления холстов.md`), холст обновить скриптом, как договорено в правилах vault.
- [ ] **Step 3: Playwright-профиль.** Некит логинится в Instagram в `data/pw-profile` (`uv run python -c` с `launch_persistent_context(headless=False)`), затем проверка `pw_fetch.py` на одном рилсе.
- [ ] **Step 4: Пилот на 5 рилсах**, включая рилс про автоматизацию Instagram: `uv run python -m reels_radar ingest <export>`, `run --limit 5`, смотреть расход и качество карточек. Калибровка `select_threshold` по реальным score.
- [ ] **Step 5: Новый экспорт.** Проверить наличие файла коллекций; если есть, добавить разбор `folder` в `export.py` отдельной задачей с тестом на реальном фрагменте.
- [ ] **Step 6: Ночь и дайджест.** `launchd`-плист (по образцу `schedules/launchd/`) на ночной `run` и воскресный `digest` + отправка в бота; плисты лежат в проекте, устанавливает Некит руками.
- [ ] **Step 7: Финальное ревью ветки** свежим ревьюером, затем merge в `main` по решению Некита.

---

## Self-Review

**Spec coverage:** поток [1-7] (Task 2,3,4,5,6,8,7), purposes и обработка `friend/content/product/claude/note` (Task 6,7,9,10), темы из YAML (Task 1), цепочка видео с Playwright (Task 4), «нужен файл» в дайджесте (Task 9) и приём видео от Некита (Task 10), бюджет и пауза по лимиту (Task 8), ошибки без падения прогона (Task 8), откат 30 дней: **отклонение** — снапшоты 30 дней из харвестера не копируются, откат реализован переносом в `.trash/` (Task 7), этого достаточно для заметок, которые только создаются, а не дописываются. Режим 2 (автозапись) спека относит на потом: в плане нет. Холсты: в плане обновляются в Task 11 Step 2 скриптом vault, не из кода (отклонение, зафиксировано).

**Placeholder scan:** «TBD/TODO» нет. Два места с условием исполнителю (структура `items_by_key.json` в Task 3, `is_limit` в Task 8) содержат явную команду проверки.

**Type consistency:** `Verdict` поля идентичны в Task 6, 7, 8; `LocalResult` в Task 5, 8, 10; статусы из Task 1 совпадают с использованием. `run_batch(fetch, local, classify)` в Task 8 совпадает с `live.py` в Task 10. `rollback(vault, db, code, themes)` в Task 7 вызывается так же в Task 10.

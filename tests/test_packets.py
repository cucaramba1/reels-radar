"""Пакеты записи: сервер просит, ноут пишет настоящими функциями, ответ возвращается и правит базу сервера."""
import shutil
from pathlib import Path
from types import SimpleNamespace

from reels_radar import packets as P
from reels_radar.config import Theme
from reels_radar.db import DB

SEC = Theme("ИИ", "ИИ работа", "ИИ работа — карта заметок.md")


def _pair(tmp_path):
    srv = SimpleNamespace(data_dir=tmp_path / "srv", vault=tmp_path / "mirror")
    home = SimpleNamespace(data_dir=tmp_path / "home", vault=tmp_path / "vault")
    for d in (srv.data_dir, home.data_dir, home.vault):
        d.mkdir(parents=True, exist_ok=True)
    db = DB(srv.data_dir / "radar.db")
    db.add_item("C1", "https://instagram.com/reel/C1/", "подпись", 1)
    db.update("C1", status="draft", theme="ИИ", purposes="note", kind="совет", summary="суть", template="структура",
              title="Заметка про промпты", body="тело заметки")
    return srv, home, db


def _transport(srv, home):
    """То, что делает rsync: outbox сервера -> inbox ноута, acks_out ноута -> acks сервера."""
    inbox = home.data_dir / "inbox"
    shutil.rmtree(inbox, ignore_errors=True)
    shutil.copytree(srv.data_dir / "outbox", inbox)


def _return_acks(srv, home):
    (srv.data_dir / "acks").mkdir(exist_ok=True)
    for f in (home.data_dir / "acks_out").glob("*.json"):
        shutil.copy(f, srv.data_dir / "acks" / f.name)


def test_note_roundtrip_writes_vault_and_updates_server(tmp_path):
    srv, home, db = _pair(tmp_path)
    P.queue(srv, db, "C1", "note", sec=P.sec_to_dict(SEC, {}))
    assert db.get("C1")["status"] == "queued"
    _transport(srv, home)
    assert P.apply_inbox(home, {}, {}) == [next((srv.data_dir / "outbox").glob("*.json")).stem]
    note = home.vault / "ИИ работа" / "Заметка про промпты.md"
    assert note.exists() and "тело заметки" in note.read_text("utf8")
    assert "[[Заметка про промпты]]" in (home.vault / "ИИ работа" / SEC.moc).read_text("utf8")
    _return_acks(srv, home)
    ev = P.read_acks(srv, db)
    assert [e["type"] for e in ev] == ["done"]
    r = db.get("C1")
    assert r["status"] == "written" and r["note_path"] == "ИИ работа/Заметка про промпты.md"
    assert not list((srv.data_dir / "outbox").glob("*.json"))  # запрос убран после ответа


def test_redelivery_does_not_write_second_note(tmp_path):
    srv, home, db = _pair(tmp_path)
    P.queue(srv, db, "C1", "note", sec=P.sec_to_dict(SEC, {}))
    _transport(srv, home)
    P.apply_inbox(home, {}, {})
    P.apply_inbox(home, {}, {})  # ноут не успел отправить ack, rsync принёс пакет ещё раз
    assert {p.name for p in (home.vault / "ИИ работа").glob("*.md")} == {"ИИ работа — карта заметок.md", "Заметка про промпты.md"}


def test_failed_write_returns_prev_status_and_event(tmp_path, monkeypatch):
    srv, home, db = _pair(tmp_path)
    P.queue(srv, db, "C1", "idea")
    _transport(srv, home)
    monkeypatch.setattr(P.D, "write_idea", lambda *a, **k: (_ for _ in ()).throw(OSError("диск полон")))
    P.apply_inbox(home, {}, {})
    _return_acks(srv, home)
    ev = P.read_acks(srv, db)
    assert ev[0]["type"] == "failed" and "диск полон" in ev[0]["error"]
    assert db.get("C1")["status"] == "draft"  # кнопки снова рабочие


def test_undo_roundtrip_moves_note_to_trash(tmp_path):
    srv, home, db = _pair(tmp_path)
    P.queue(srv, db, "C1", "note", sec=P.sec_to_dict(SEC, {}))
    _transport(srv, home); P.apply_inbox(home, {}, {}); _return_acks(srv, home); P.read_acks(srv, db)
    shutil.rmtree(srv.data_dir / "acks"); shutil.rmtree(home.data_dir / "acks_out")
    P.queue(srv, db, "C1", "undo")
    _transport(srv, home); P.apply_inbox(home, {"ИИ": SEC}, {}); _return_acks(srv, home)
    ev = P.read_acks(srv, db)
    assert ev[0]["type"] == "done"
    assert db.get("C1")["status"] == "draft" and db.get("C1")["note_path"] is None
    assert not (home.vault / "ИИ работа" / "Заметка про промпты.md").exists()
    assert (home.vault / ".trash" / "ИИ работа" / "Заметка про промпты.md").exists()


def test_section_vault_key_roundtrip(tmp_path):
    vaults = {"dosug": str(tmp_path / "mirror-extra")}
    sec = Theme("Фитнес", "Фитнес", "Фитнес — карта заметок.md", str(tmp_path / "mirror-extra"))
    d = P.sec_to_dict(sec, vaults)
    assert d["vault"] == "dosug"
    home_sec = P.dict_to_sec(d, {"dosug": str(tmp_path / "real-dosug")})  # на ноуте тот же ключ ведёт в настоящий vault
    assert home_sec.vault == str(tmp_path / "real-dosug")
    assert P.dict_to_sec(P.sec_to_dict(SEC, vaults), vaults).vault is None


class _Bot:
    def __init__(self):
        self.edited, self.sent = [], []

    async def edit_message_text(self, text, chat_id, message_id, reply_markup):
        self.edited.append((chat_id, message_id, text, reply_markup))

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_notify_acks_edits_known_card_and_reports_failures(tmp_path):
    import asyncio
    from reels_radar.bot import notify_acks
    srv, _, db = _pair(tmp_path)
    srv.owner_id = 7
    db.update("C1", status="written", decision="note:ИИ работа")
    db.kv_set("card:C1", "7:55")
    bot = _Bot()
    asyncio.run(notify_acks(bot, srv, db, [{"type": "done", "code": "C1", "kind": "note", "msg": "записано"}]))
    assert bot.edited and bot.edited[0][:2] == (7, 55) and not bot.sent
    asyncio.run(notify_acks(bot, srv, db, [{"type": "failed", "code": "C1", "kind": "note", "error": "диск полон"}]))
    assert "диск полон" in bot.sent[0][1]
    db.kv_set("card:C1", "")  # карточка потеряна: пишем отдельным сообщением
    asyncio.run(notify_acks(bot, srv, db, [{"type": "done", "code": "C1", "kind": "note", "msg": "записано: Х"}]))
    assert "записано: Х" in bot.sent[-1][1]


def test_router_builds_in_packet_mode(db, tmp_path, monkeypatch):
    from reels_radar.bot import router
    from reels_radar.sources.db import SourcesDB
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "themes.yaml").write_text("vaults: {dosug: '/x'}\nthemes: {}\n", "utf8")
    monkeypatch.setenv("APPLY_MODE", "packet")
    s = SimpleNamespace(owner_id=1, vault=tmp_path, data_dir=tmp_path, root=tmp_path)
    rt = router(s, db, {"ИИ": SEC}, SourcesDB(tmp_path / "s.db"))
    assert {h.callback.__name__ for h in rt.callback_query.handlers} >= {"cb", "acb"}

"""Пакеты записи в vault: сервер просит, ноут пишет теми же функциями decisions.py и vault.py, ответ (ack) возвращается.

Сервер (APPLY_MODE=packet): queue() кладёт запрос в data/outbox, карточка получает статус queued, read_acks() применяет ответы.
Ноут: apply_packet() собирает временную базу из одной строки и вызывает настоящие write_note_to / write_idea /
write_inspiration / undo, поэтому формат заметок, MOC и холстов не меняется. Повторная доставка безопасна: журнал
data/applied хранит ответ на каждый ключ, второй раз в vault ничего не пишется.
Всегда инициирует ноут (ssh/rsync наружу), сервер к ноуту не подключается."""
from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
from pathlib import Path

from . import decisions as D
from .config import Theme
from .db import DB

log = logging.getLogger(__name__)

ROW_FIELDS = ("url", "caption", "theme", "purposes", "kind", "summary", "template", "title", "body", "status",
              "note_path", "note_created", "note_vault", "moc_rel", "canvas_rel", "moc_line", "decision")
ACK_FIELDS = ("status", "note_path", "note_created", "note_vault", "moc_rel", "canvas_rel", "moc_line", "decision")


def packet_mode() -> bool:
    return os.environ.get("APPLY_MODE") == "packet"


def _atomic_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), "utf-8")
    os.replace(tmp, path)  # ноут не должен увидеть половину файла


# --- разделы между серверным зеркалом и настоящим vault -------------------------------------------------------

def sec_to_dict(sec: Theme, vaults: dict[str, str]) -> dict:
    """Путь vault на сервере (зеркало) не годится ноуту: передаём ключ из themes.yaml, main = основной vault."""
    key = "main"
    if sec.vault:
        key = next((k for k, v in vaults.items() if Path(v) == Path(sec.vault)), None)
        if key is None:
            raise ValueError(f"vault {sec.vault} не описан в themes.yaml")
    return {"name": sec.name, "folder": sec.folder, "moc": sec.moc, "canvas": sec.canvas, "vault": key}


def dict_to_sec(d: dict, vaults: dict[str, str]) -> Theme:
    return Theme(d["name"], d["folder"], d["moc"], None if d["vault"] == "main" else vaults[d["vault"]], d.get("canvas"))


# --- сервер ----------------------------------------------------------------------------------------------------

def queue(s, db, code: str, kind: str, **params) -> str:
    """kind: note | idea | inspo | undo. Статус queued до ответа ноута; при ошибке вернём прежний."""
    r = db.get(code)
    seq = int(db.kv_get("pkseq", "0")) + 1
    db.kv_set("pkseq", seq)
    key = f"{kind}-{code}-{seq}"
    out = Path(s.data_dir) / "outbox"
    out.mkdir(parents=True, exist_ok=True)
    _atomic_json(out / f"{key}.json", {"key": key, "kind": kind, "code": code, "params": params,
                                       "prev_status": r["status"], "row": {k: r[k] for k in ROW_FIELDS}})
    db.update(code, status="queued")
    return "⏳ в очереди на запись (до 5 минут)"


def read_acks(s, db) -> list[dict]:
    """Ответы ноута -> база сервера. Возвращает события для бота: done | failed."""
    events: list[dict] = []
    acks = Path(s.data_dir) / "acks"
    if not acks.exists():
        return events
    done_dir, out = acks / "done", Path(s.data_dir) / "outbox"
    for f in sorted(acks.glob("*.json")):
        try:
            ack = json.loads(f.read_text("utf-8"))
        except ValueError:
            log.error("битый ack %s, пропускаю", f.name)
            continue
        key, code = ack["key"], ack["code"]
        if db.get(code) is not None and db.kv_get(f"pkdone:{key}") is None:
            if ack["ok"]:
                db.update(code, **{k: v for k, v in ack["fields"].items() if k in ACK_FIELDS})
                events.append({"type": "done", "code": code, "kind": ack["kind"], "msg": ack.get("msg", "")})
            else:
                db.update(code, status=ack.get("prev_status") or "draft")  # кнопки снова рабочие
                events.append({"type": "failed", "code": code, "kind": ack["kind"], "error": ack.get("error", "")})
            db.kv_set(f"pkdone:{key}", "1")
        (out / f"{key}.json").unlink(missing_ok=True)  # ноут ответил, запрос больше не нужен
        done_dir.mkdir(exist_ok=True)
        os.replace(f, done_dir / f.name)
    return events


# --- ноут ------------------------------------------------------------------------------------------------------

def apply_packet(s, themes, vaults: dict[str, str], packet: dict) -> dict:
    """Пакет -> ack. Ошибки записи не бросает, а возвращает в ack (ok=False), чтобы сервер показал их Некиту."""
    key, kind, code = packet["key"], packet["kind"], packet["code"]
    base = {"key": key, "kind": kind, "code": code, "prev_status": packet.get("prev_status")}
    try:
        db = DB(":memory:")
        db.add_item(code, packet["row"]["url"], packet["row"].get("caption") or "", 0)
        db.update(code, **packet["row"])
        vault, p = Path(s.vault), packet.get("params") or {}
        if kind == "note":
            msg = D.write_note_to(db, code, dict_to_sec(p["sec"], vaults), vault, p.get("intro", ""))
        elif kind == "idea":
            msg = D.write_idea(db, code, vault)
        elif kind == "inspo":
            msg = D.write_inspiration(db, code, p["kind"], vault)
        elif kind == "undo":
            msg = D.undo(db, code, vault, themes)
        else:
            return {**base, "ok": False, "error": f"неизвестный тип пакета: {kind}"}
        r = db.get(code)
        return {**base, "ok": True, "msg": msg, "fields": {k: r[k] for k in ACK_FIELDS}}
    except Exception as e:  # noqa: BLE001 диск, права, битый холст: сервер покажет текст, пакет можно послать заново
        log.exception("apply %s", key)
        return {**base, "ok": False, "error": f"{type(e).__name__}: {e}"}


def apply_inbox(s, themes, vaults) -> list[str]:
    """Все пакеты из data/inbox -> data/acks_out/<key>.json. Журнал data/applied делает повторную доставку безопасной."""
    data = Path(s.data_dir)
    inbox, acks_out, ledger = data / "inbox", data / "acks_out", data / "applied"
    acks_out.mkdir(parents=True, exist_ok=True)
    ledger.mkdir(parents=True, exist_ok=True)
    done = []
    for f in sorted(inbox.glob("*.json")) if inbox.exists() else []:
        try:
            packet = json.loads(f.read_text("utf-8"))
        except ValueError:
            log.error("битый пакет %s, пропускаю", f.name)
            continue
        key = packet["key"]
        if (ledger / f"{key}.json").exists():
            ack = json.loads((ledger / f"{key}.json").read_text("utf-8"))  # уже писали: тот же ответ, vault не трогаем
        else:
            ack = apply_packet(s, themes, vaults, packet)
            if ack["ok"]:
                _atomic_json(ledger / f"{key}.json", ack)
        _atomic_json(acks_out / f"{key}.json", ack)
        done.append(key)
    return done


def run_applier(s, themes, vaults, run=subprocess.run) -> dict:
    """Ноут: забрать пакеты с сервера, применить, отправить ответы. launchd раз в 5 минут (зеркало vault делает applier харвестера)."""
    rep: dict = {"applied": [], "skipped": None}
    host, key, root = os.environ.get("REMOTE_HOST"), os.environ.get("REMOTE_KEY"), os.environ.get("REMOTE_ROOT", "reels-radar")
    if not host or not key:
        rep["skipped"] = "REMOTE_HOST/REMOTE_KEY не заданы"
        return rep
    ssh = f"ssh -i {shlex.quote(key)} -o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=10"
    data = Path(s.data_dir)

    def rsync(*args: str):
        return run(["rsync", "-a", "-e", ssh, *args], capture_output=True, text=True)

    r = run([*shlex.split(ssh), host, f"mkdir -p {root}/data/acks {root}/data/outbox"], capture_output=True, text=True)
    if r.returncode != 0:
        rep["skipped"] = f"сервер недоступен: {r.stderr.strip()[-120:]}"
        return rep
    (data / "inbox").mkdir(parents=True, exist_ok=True)
    r = rsync("--delete", "--exclude=*.tmp", f"{host}:{root}/data/outbox/", f"{data / 'inbox'}/")
    if r.returncode != 0:
        rep["skipped"] = f"не забрал пакеты (rsync {r.returncode}): {r.stderr.strip()[-120:]}"
        return rep
    rep["applied"] = apply_inbox(s, themes, vaults)
    out = data / "acks_out"
    if out.exists() and any(out.glob("*.json")):
        r = rsync("--remove-source-files", f"{out}/", f"{host}:{root}/data/acks/")
        if r.returncode != 0:  # ответы остаются на диске, уйдут в следующий раз; записанное повторно не запишется
            log.error("ответы не ушли (rsync %s): %s", r.returncode, r.stderr.strip()[-200:])
    return rep

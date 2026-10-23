from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .cards import HELP, done_menu, idea_menu, inspo_menu, keyboard_spec, note_menu, parse_callback, render_card, section_cb
from .decisions import decision_label, find_section, new_section, proposed, reject, sec_hash, undo, write_idea, write_inspiration, write_note_to
from .sources.cards import account_keyboard, account_text, chunk_lines, parse_account_cb
from .sources.cleanup import apply_action as acc_action, candidates, export_cleanup, marked
from .sources.db import SourcesDB
from .vault import catalog, rollback


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


def router(s, db, themes, sdb=None) -> Router:
    rt = Router()
    owner = F.from_user.id == s.owner_id

    def akb(u):
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
                                                     for row in account_keyboard(u)])

    @rt.callback_query(F.data.startswith("ac:"), owner)
    async def acb(q: CallbackQuery):
        action, user = parse_account_cb(q.data)
        msg = acc_action(sdb, user, action)
        await q.message.edit_reply_markup(reply_markup=None)
        await q.answer(msg)

    @rt.message(Command("cleanup"), owner)
    async def cleanup(m: Message):
        rows = candidates(sdb, 10)
        if not rows:
            await m.answer("кандидатов на чистку нет")
        for r in rows:
            await m.answer(account_text(r), reply_markup=akb(r["username"]))

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

    def mk(rows):
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
                                                     for row in rows if row])

    def sections():
        return catalog(s.vault, themes)

    async def finish(q: CallbackQuery, code: str, msg: str):
        r = db.get(code)
        await q.message.edit_text(render_card(r), reply_markup=mk(done_menu(decision_label(r), code)))
        await q.answer(msg)

    @rt.callback_query(owner)
    async def cb(q: CallbackQuery):
        action, rest = parse_callback(q.data)
        code = rest.split(":")[-1] if action == "ns" else rest
        r = db.get(code)
        if not r:
            await q.answer("карточка не найдена")
            return
        if action in ("info",):
            await q.answer(decision_label(r))
        elif action == "u":
            msg = undo(db, code, s.vault, themes)
            await q.message.edit_text(render_card(db.get(code)), reply_markup=kb(code))
            await q.answer(msg)
        elif action not in ("n", "i", "s", "f", "x", "nk", "nc", "nl", "nn", "ns", "ik", "ie", "sv", "sm", "si", "b"):
            await q.answer("старая карточка, жди новую")
        elif r["status"] != "draft":
            await q.answer("уже обработано: жми ↩️, чтобы вернуть")
        elif action == "b":
            await q.message.edit_text(render_card(r), reply_markup=kb(code))
            await q.answer()
        elif action == "n":
            p = proposed(list(themes.values()), r)
            can = r["theme"] if not p and r["theme"] != "Разное" else None
            await q.message.edit_reply_markup(reply_markup=mk(note_menu(code, p.folder if p else None, can)))
            await q.answer()
        elif action == "nk":
            p = proposed(list(themes.values()), r)
            await finish(q, code, write_note_to(db, code, p, s.vault) if p else "раздел не найден")
        elif action == "nc":
            await finish(q, code, write_note_to(db, code, new_section(r["theme"], next((t.vault for t in themes.values() if t.vault), None)), s.vault))
        elif action == "nl":
            rows = [[InlineKeyboardButton(text=t.folder, callback_data=section_cb(sec_hash(t), code))] for t in sections()]
            rows.append([InlineKeyboardButton(text="⬅️", callback_data=f"b:{code}")])
            await q.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            await q.answer()
        elif action == "ns":
            sec = find_section(sections(), rest.split(":")[0])
            await finish(q, code, write_note_to(db, code, sec, s.vault) if sec else "раздел не найден")
        elif action == "nn":
            db.kv_set("await", f"new:{code}")
            await q.message.answer("Напиши одним сообщением: первая строка название нового холста, дальше что туда складывать.")
            await q.answer()
        elif action == "i":
            await q.message.edit_text(render_card(r, True), reply_markup=mk(idea_menu(code)))
            await q.answer()
        elif action == "ik":
            await finish(q, code, write_idea(db, code, s.vault))
        elif action == "ie":
            db.kv_set("await", f"edit:{code}")
            await q.message.answer("Пришли новую структуру рилса одним сообщением, она заменит текущую.")
            await q.answer()
        elif action == "s":
            await q.message.edit_reply_markup(reply_markup=mk(inspo_menu(code)))
            await q.answer()
        elif action in ("sv", "sm", "si"):
            kind = {"sv": "visual", "sm": "memes", "si": "ideas"}[action]
            await finish(q, code, write_inspiration(db, code, kind, s.vault))
        elif action in ("f", "x"):
            await finish(q, code, reject(db, code, "friend" if action == "f" else "reject"))

    @rt.message(Command("help"), owner)
    async def help_(m: Message):
        await m.answer(HELP)

    @rt.message(owner, F.text, ~F.text.startswith("/"))
    async def free_text(m: Message):
        kind, _, code = (db.kv_get("await") or "").partition(":")
        if not code or not db.get(code):
            return
        db.kv_set("await", "")
        if kind == "edit":
            db.update(code, template=m.text.strip())
            await m.answer(render_card(db.get(code), True), reply_markup=mk(idea_menu(code)))
        elif kind == "new":
            name, _, intro = m.text.strip().partition("\n")
            sec = new_section(name)
            msg = write_note_to(db, code, sec, s.vault, intro)
            r = db.get(code)
            await m.answer(f"{msg} (холст «{sec.folder}»)", reply_markup=mk(done_menu(decision_label(r), code)))

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
    dp.include_router(router(s, db, themes, SourcesDB(s.data_dir / "sources.db")))

    async def pump():
        while True:
            try:
                await send_pending(bot, db, s.owner_id)
            except Exception:
                pass
            await asyncio.sleep(300)

    task = asyncio.create_task(pump())
    try:
        await dp.start_polling(bot)
    finally:
        task.cancel()

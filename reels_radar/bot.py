from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .cards import keyboard_spec, parse_callback, render_card, theme_cb
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
            rows = [[InlineKeyboardButton(text=n, callback_data=theme_cb(i, code))] for i, n in enumerate(themes)]
            await q.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        elif action == "st":
            idx, code = code.split("|", 1)
            apply_action(db, code, f"set_theme:{list(themes)[int(idx)]}", themes, s.vault)
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

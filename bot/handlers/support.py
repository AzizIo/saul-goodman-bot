"""Поддержка Saul Goodman ⚖️."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
from bot import db as db_module
from bot import keyboards as kb
from bot import services
from bot import texts
from bot.states import Support


def build_router(database: db_module.Database) -> Router:
    router = Router(name="support")

    @router.message(F.text == kb.BTN_SUPPORT)
    async def start_support(message: Message, state: FSMContext) -> None:
        await state.clear()
        if message.from_user is None:
            return
        record = database.get_user(message.from_user.id)
        if record is None:
            await message.answer(texts.pending_review(), parse_mode=config.PARSE_MODE)
            return
        await state.set_state(Support.waiting_for_support_msg)
        await message.answer(texts.support_prompt(), reply_markup=kb.cancel(), parse_mode=config.PARSE_MODE)

    @router.message(Support.waiting_for_support_msg, F.text)
    async def receive_support(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return
        text = (message.text or "").strip()
        if not text:
            await message.answer("⚠️ Пустое сообщение. Опиши проблему текстом.")
            return
        ticket_id = database.create_ticket(message.from_user.id, text[:3000])
        await state.clear()
        await message.answer(
            texts.support_sent(ticket_id),
            reply_markup=kb.back_to_menu(),
            parse_mode=config.PARSE_MODE,
        )
        await services.notify_admin(
            message.bot,
            "🆘 <b>Обращение #{}</b>\n\n"
            "👤 ID: <code>{}</code>\n\n"
            "💬 {}".format(ticket_id, message.from_user.id, text[:3000])
            + f"\n\nОтветить: <code>/reply_{ticket_id} текст</code>",
        )

    return router
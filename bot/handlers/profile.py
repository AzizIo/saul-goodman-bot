"""Профиль и статистика Saul Goodman ⚖️."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from bot import db as db_module
from bot import keyboards as kb
from bot import services
from bot import texts


def build_router(database: db_module.Database) -> Router:
    router = Router(name="profile")

    def profile_view(user_id: int) -> str | None:
        record = database.get_user(user_id)
        if record is None:
            return None
        stats = database.user_stats(user_id)
        return texts.profile(
            user_id,
            int(record["balance"]),
            int(record["available"]),
            stats,
            database.operator_stats(user_id),
        )

    def stats_view(user_id: int) -> str:
        stats_all = database.user_stats(user_id)
        return texts.statistics(
            database.stats_last_24h(user_id),
            database.operator_stats(user_id),
            stats_all.get("failed", 0),
            database.fail_reasons(user_id),
        )

    @router.message(F.text == kb.BTN_PROFILE)
    async def show_profile(message: Message, state: FSMContext) -> None:
        await state.clear()
        if message.from_user is None:
            return
        view = profile_view(message.from_user.id)
        if view is None:
            await message.answer(texts.pending_review(), parse_mode=config.PARSE_MODE)
            return
        await message.answer(view, reply_markup=kb.profile_actions(), parse_mode=config.PARSE_MODE)

    @router.message(F.text == kb.BTN_STATS)
    async def show_stats(message: Message, state: FSMContext) -> None:
        await state.clear()
        if message.from_user is None:
            return
        if database.get_user(message.from_user.id) is None:
            await message.answer(texts.pending_review(), parse_mode=config.PARSE_MODE)
            return
        await message.answer(
            stats_view(message.from_user.id),
            reply_markup=kb.back_to_menu(),
            parse_mode=config.PARSE_MODE,
        )

    @router.callback_query(F.data == "refresh_profile")
    async def refresh_profile(call: CallbackQuery) -> None:
        if call.from_user is None or call.message is None:
            return
        view = profile_view(call.from_user.id)
        if view is None:
            await call.answer("Профиль не найден", show_alert=True)
            return
        await services.safe_edit(call.message, view, reply_markup=kb.profile_actions())
        await call.answer("Обновлено")

    return router
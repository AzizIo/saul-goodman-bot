"""Старт, проверка подписки и главное меню Saul Goodman ⚖️."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from bot import db as db_module
from bot import keyboards as kb
from bot import services
from bot import texts
from bot.filters import IsAdmin


def build_router(database: db_module.Database) -> Router:
    router = Router(name="common")

    @router.message(CommandStart(), F.chat.type == "private")
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        user = message.from_user
        if user is None:
            return

        # 1-2. подписка на канал
        if not await services.is_subscribed(message.bot, user.id):
            await message.answer(
                texts.subscription_required(),
                reply_markup=kb.subscription(),
                parse_mode=config.PARSE_MODE,
            )
            return

        # 3. регистрация со статусом pending
        record = database.get_user(user.id)
        created = database.create_user(user.id, user.username)
        record = database.get_user(user.id)
        if record is None:
            await message.answer("⚠️ Не удалось открыть кабинет. Попробуй позже.")
            return

        # скрытое обновление username
        if not created and user.username and record["username"] != user.username:
            try:
                database.set_username(user.id, user.username)
            except Exception:  # noqa: BLE001
                pass

        # 4. уведомление администратору о новой заявке
        if created:
            await services.notify_admin(
                message.bot,
                "🆕 <b>Новая заявка</b>\n\n"
                f"ID: <code>{user.id}</code>\n"
                f"Имя: {user.full_name}\n"
                f"Username: @{user.username or '—'}\n\n"
                f"Одобрить: <code>/approve_{user.id}</code>\n"
                f"Забанить: <code>/ban_{user.id}</code>",
            )

        # 5. pending
        if record["status"] == db_module.USER_PENDING:
            await message.answer(texts.pending_review(), parse_mode=config.PARSE_MODE)
            return
        # 6. banned
        if record["status"] == db_module.USER_BANNED:
            await message.answer(texts.banned(), parse_mode=config.PARSE_MODE)
            return

        # 7. active
        await message.answer(
            texts.main_menu(user.first_name),
            reply_markup=kb.main_reply(is_admin=(user.id == config.ADMIN_ID)),
            parse_mode=config.PARSE_MODE,
        )

    @router.callback_query(F.data == "check_sub")
    async def check_sub(call: CallbackQuery, state: FSMContext) -> None:
        if call.from_user is None:
            return
        if not await services.is_subscribed(call.bot, call.from_user.id):
            await call.answer("Ты ещё не подписан 🙅", show_alert=True)
            return
        await call.answer("Подписка подтверждена ✅")
        await state.clear()
        record = database.get_user(call.from_user.id)
        if record is None:
            database.create_user(call.from_user.id, call.from_user.username)
            record = database.get_user(call.from_user.id)
            if record is not None:
                await services.notify_admin(
                    call.bot,
                    "🆕 <b>Новая заявка</b>\n\n"
                    f"ID: <code>{call.from_user.id}</code>\n"
                    f"Одобрить: <code>/approve_{call.from_user.id}</code>",
                )
        if call.message:
            try:
                await call.message.delete()
            except Exception:  # noqa: BLE001
                pass
        if call.from_user.id == config.ADMIN_ID or (record is not None and record["status"] == db_module.USER_ACTIVE):
            await call.message.answer(  # type: ignore[union-attr]
                texts.main_menu(call.from_user.first_name),
                reply_markup=kb.main_reply(is_admin=(call.from_user.id == config.ADMIN_ID)),
                parse_mode=config.PARSE_MODE,
            )
        elif record is not None and record["status"] == db_module.USER_BANNED:
            await call.message.answer(texts.banned(), parse_mode=config.PARSE_MODE)  # type: ignore[union-attr]
        else:
            await call.message.answer(texts.pending_review(), parse_mode=config.PARSE_MODE)  # type: ignore[union-attr]

    @router.callback_query(F.data == "back_menu")
    async def back_menu(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await call.answer()
        if call.message is None or call.from_user is None:
            return
        record = database.get_user(call.from_user.id)
        if record is None or (record["status"] != db_module.USER_ACTIVE and call.from_user.id != config.ADMIN_ID):
            await call.message.answer(texts.pending_review(), parse_mode=config.PARSE_MODE)
            return
        await call.message.answer(
            texts.main_menu(call.from_user.first_name),
            reply_markup=kb.main_reply(is_admin=(call.from_user.id == config.ADMIN_ID)),
            parse_mode=config.PARSE_MODE,
        )

    @router.message(Command("help"), F.chat.type == "private")
    async def help_cmd(message: Message) -> None:
        await message.answer(
            "⚖️ <b>Как это работает</b>\n\n"
            "1. Подпишись на канал и дождись одобрения.\n"
            "2. Жми «⚖️ Начать сделку», выбери оператора, отправь фото QR с номером в подписи.\n"
            "3. Следи за заказом в «💼 Профиль» и «📊 Статистика».\n"
            "4. Выводи деньги кнопкой «💳 Вывести».\n\n"
            "Вопросы — «🆘 Поддержка».",
            parse_mode=config.PARSE_MODE,
        )

    @router.message(Command("id"))
    async def id_cmd(message: Message) -> None:
        if message.from_user:
            await message.answer(
                f"🆔 Твой ID: <code>{message.from_user.id}</code>",
                parse_mode=config.PARSE_MODE,
            )

    @router.message(Command("admin"), F.chat.type == "private", IsAdmin())
    async def admin_shortcut(message: Message) -> None:
        state_db = database.operators_state(config.OPERATORS)
        await message.answer(
            texts.admin_panel(database.global_stats(), state_db),
            reply_markup=kb.admin_panel(state_db),
            parse_mode=config.PARSE_MODE,
        )

    return router
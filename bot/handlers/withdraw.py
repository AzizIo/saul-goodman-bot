"""Вывод средств Saul Goodman ⚖️."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from bot import db as db_module
from bot import keyboards as kb
from bot import services
from bot import texts
from bot.states import Withdraw
from bot.validators import parse_wallet


def build_router(database: db_module.Database) -> Router:
    router = Router(name="withdraw")
    min_cents = config.to_cents(config.MIN_WITHDRAWAL)

    @router.callback_query(F.data == "withdraw")
    async def start_withdraw(call: CallbackQuery, state: FSMContext) -> None:
        if call.from_user is None:
            return
        record = database.get_user(call.from_user.id)
        if record is None or record["status"] != db_module.USER_ACTIVE:
            await call.answer("Доступ не подтверждён", show_alert=True)
            return
        available = int(record["available"])
        if available < min_cents:
            await call.answer()
            if call.message:
                await call.message.answer(
                    texts.withdraw_no_funds(min_cents, available),
                    parse_mode=config.PARSE_MODE,
                )
            return
        await state.set_state(Withdraw.waiting_for_withdraw_wallet)
        await call.answer()
        if call.message:
            await call.message.answer(
                texts.withdraw_prompt(min_cents),
                reply_markup=kb.cancel(),
                parse_mode=config.PARSE_MODE,
            )

    @router.message(Withdraw.waiting_for_withdraw_wallet, F.text)
    async def receive_wallet(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return
        record = database.get_user(message.from_user.id)
        if record is None or record["status"] != db_module.USER_ACTIVE:
            await state.clear()
            await message.answer(texts.pending_review(), parse_mode=config.PARSE_MODE)
            return

        parsed = parse_wallet(message.text or "")
        if parsed is None:
            await message.answer(texts.withdraw_bad_wallet(), reply_markup=kb.cancel(),
                                 parse_mode=config.PARSE_MODE)
            return

        network, wallet = parsed
        available = int(record["available"])
        if available < min_cents:
            await state.clear()
            await message.answer(texts.withdraw_no_funds(min_cents, available),
                                 parse_mode=config.PARSE_MODE)
            return

        amount = available  # заявка фиксирует сумму в момент создания
        wid = database.create_withdrawal(message.from_user.id, amount, wallet, network)
        await state.clear()
        if wid is None:
            await message.answer(texts.withdraw_no_funds(min_cents, available), parse_mode=config.PARSE_MODE)
            return

        await message.answer(
            texts.withdraw_created(wid, amount, network, wallet),
            reply_markup=kb.back_to_menu(),
            parse_mode=config.PARSE_MODE,
        )
        await services.notify_admin(
            message.bot,
            "💳 <b>Заявка на вывод #{}</b>\n\n"
            "👤 ID: <code>{}</code>\n"
            "💵 Сумма: <b>{}</b>\n"
            "🌐 Сеть: <b>{}</b>\n"
            "🏦 Кошелёк: <code>{}</code>\n\n"
            "Перевести и подтвердить: <code>/yes_{}</code>\n"
            "Отклонить: <code>/reject_{}</code>".format(
                wid, message.from_user.id, texts.money(amount), network, wallet, wid, wid
            ),
        )

    @router.message(Withdraw.waiting_for_withdraw_wallet)
    async def wallet_wrong_type(message: Message) -> None:
        await message.answer("⚠️ Нужен текстовый адрес кошелька.", reply_markup=kb.cancel())

    @router.callback_query(F.data == "cancel_fsm")
    async def cancel(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await call.answer("Отменено")
        if call.message:
            try:
                await call.message.delete()
            except Exception:  # noqa: BLE001
                pass
            await call.message.answer("⚖️ Отменили. Возвращайся, когда будешь готов.",
                                      reply_markup=kb.back_to_menu(), parse_mode=config.PARSE_MODE)

    return router
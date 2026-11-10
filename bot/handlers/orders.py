"""Приёмка QR/eSIM Saul Goodman ⚖️."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from bot import db as db_module
from bot import keyboards as kb
from bot import services
from bot import texts
from bot.states import Deal
from bot.validators import normalize_phone

log = logging.getLogger("saul.orders")


def build_router(database: db_module.Database) -> Router:
    router = Router(name="orders")

    def operator_catalog() -> list[tuple[str, bool, int]]:
        state = database.operators_state(config.OPERATORS)
        return [
            (name, state.get(name, meta.get("open", True)), config.operator_price_cents(name))
            for name, meta in config.OPERATORS.items()
        ]

    async def ensure_active(user_id: int) -> bool:
        record = database.get_user(user_id)
        return record is not None and record["status"] == db_module.USER_ACTIVE

    @router.message(F.text == kb.BTN_DEAL)
    async def start_deal(message: Message, state: FSMContext) -> None:
        await state.clear()
        if message.from_user is None or not await ensure_active(message.from_user.id):
            await message.answer(texts.pending_review(), parse_mode=config.PARSE_MODE)
            return
        await message.answer(
            texts.choose_operator(),
            reply_markup=kb.operators(operator_catalog()),
            parse_mode=config.PARSE_MODE,
        )

    @router.callback_query(F.data == "op_closed")
    async def closed_operator(call: CallbackQuery) -> None:
        await call.answer("🔴 Приём по этому оператору закрыт", show_alert=True)

    @router.callback_query(F.data.startswith("op:"))
    async def choose_operator(call: CallbackQuery, state: FSMContext) -> None:
        if call.from_user is None or call.data is None:
            return
        operator = call.data.split(":", 1)[1]
        if operator not in config.OPERATORS:
            await call.answer("Такого оператора нет", show_alert=True)
            return
        if not await ensure_active(call.from_user.id):
            await call.answer("Доступ ещё не подтверждён", show_alert=True)
            return
        state_db = database.operators_state(config.OPERATORS)
        if not state_db.get(operator, False):
            await call.answer(f"🔴 {operator} — приём закрыт", show_alert=True)
            return
        price = config.operator_price_cents(operator)
        await state.set_state(Deal.waiting_for_qr)
        await state.update_data(operator=operator, price=price)
        await call.answer()
        if call.message:
            try:
                await call.message.delete()
            except Exception:  # noqa: BLE001
                pass
            await call.message.answer(  # type: ignore[union-attr]
                texts.ask_qr(operator, price),
                reply_markup=kb.cancel(),
                parse_mode=config.PARSE_MODE,
            )

    @router.message(Deal.waiting_for_qr, F.photo)
    async def receive_qr(message: Message, state: FSMContext) -> None:
        if message.from_user is None:
            return
        if not await ensure_active(message.from_user.id):
            await state.clear()
            await message.answer(texts.pending_review(), parse_mode=config.PARSE_MODE)
            return

        phone = normalize_phone(message.caption or "")
        if phone is None:
            await message.answer(
                texts.qr_bad_caption(),
                reply_markup=kb.cancel(),
                parse_mode=config.PARSE_MODE,
            )
            return

        data = await state.get_data()
        operator = data.get("operator")
        price = int(data.get("price") or 0)
        if not operator or operator not in config.OPERATORS:
            await state.clear()
            await message.answer(texts.choose_operator(), reply_markup=kb.operators(operator_catalog()),
                                 parse_mode=config.PARSE_MODE)
            return
        if not database.operators_state(config.OPERATORS).get(operator, False):
            await state.clear()
            await message.answer(texts.operator_closed(operator), parse_mode=config.PARSE_MODE)
            return

        file_id = message.photo[-1].file_id
        order_id = database.create_order(message.from_user.id, operator, price, phone, file_id)
        qr_path = await services.store_qr_file(message.bot, file_id, order_id)
        if qr_path:
            database.set_order_qr_path(order_id, qr_path)
        await state.clear()

        await message.answer(
            texts.order_accepted(order_id, price),
            reply_markup=kb.back_to_menu(),
            parse_mode=config.PARSE_MODE,
        )

        # фото и сведения — администратору
        caption = (
            f"📦 <b>Новый заказ #{order_id}</b>\n\n"
            f"👤 ID: <code>{message.from_user.id}</code>\n"
            f"📱 Оператор: <b>{operator}</b>\n"
            f"☎️ Номер: <code>{phone}</code>\n"
            f"💵 Сумма: {texts.money(price)}\n\n"
            f"/ok_{order_id} · /progress_{order_id} · /no_{order_id} причина"
        )
        if config.ADMIN_ID:
            try:
                await message.bot.send_photo(
                    config.ADMIN_ID, file_id, caption=caption, parse_mode=config.PARSE_MODE
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("не удалось переслать QR админу: %s", exc)
                await services.notify_admin(message.bot, caption)

    @router.message(Deal.waiting_for_qr)
    async def wrong_content(message: Message) -> None:
        await message.answer(texts.qr_wrong_content(), reply_markup=kb.cancel(), parse_mode=config.PARSE_MODE)

    return router
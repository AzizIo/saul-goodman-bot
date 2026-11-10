"""Админ-панель и админ-команды Saul Goodman ⚖️.

Все обработчики защищены фильтром IsAdmin: только ADMIN_ID и только в личке.
"""
from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from bot import db as db_module
from bot import keyboards as kb
from bot import services
from bot import texts
from bot.filters import IsAdmin, cmd
from bot.states import Admin

log = logging.getLogger("saul.admin")

CMD_RE = re.compile(r"^/(ok|no|progress|reply|approve|ban|yes|reject)(?:_(\d+))?\s*(.*)$", re.IGNORECASE | re.DOTALL)


def build_router(database: db_module.Database) -> Router:
    router = Router(name="admin")
    router.message.filter(IsAdmin())
    router.callback_query.filter(IsAdmin())

    # --- панель -----------------------------------------------------------

    def panel_text() -> str:
        return texts.admin_panel(database.global_stats(), database.operators_state(config.OPERATORS))

    async def show_panel(message: Message) -> None:
        state_db = database.operators_state(config.OPERATORS)
        await message.answer(
            texts.admin_panel(database.global_stats(), state_db),
            reply_markup=kb.admin_panel(state_db),
            parse_mode=config.PARSE_MODE,
        )

    @router.message(F.text == kb.BTN_ADMIN)
    async def open_panel(message: Message, state: FSMContext) -> None:
        await state.clear()
        await show_panel(message)

    @router.callback_query(F.data == "adm:refresh")
    async def refresh_panel(call: CallbackQuery) -> None:
        if call.message is None:
            await call.answer()
            return
        state_db = database.operators_state(config.OPERATORS)
        await services.safe_edit(call.message, panel_text(), reply_markup=kb.admin_panel(state_db))
        await call.answer("Обновлено")

    @router.callback_query(F.data.startswith("adm:op:"))
    async def toggle_operator(call: CallbackQuery) -> None:
        if call.data is None or call.message is None:
            await call.answer()
            return
        parts = call.data.split(":", 3)
        if len(parts) != 4:
            await call.answer("Некорректная команда", show_alert=True)
            return
        _, _, action, operator = parts
        if operator not in config.OPERATORS:
            await call.answer("Неизвестный оператор", show_alert=True)
            return
        database.set_operator_open(operator, action == "open")
        state_db = database.operators_state(config.OPERATORS)
        await services.safe_edit(call.message, panel_text(), reply_markup=kb.admin_panel(state_db))
        await call.answer(f"{operator}: {'приём открыт 🟢' if action == 'open' else 'приём закрыт 🔴'}")

    @router.callback_query(F.data == "adm:users")
    async def users_list(call: CallbackQuery) -> None:
        if call.message is None:
            await call.answer()
            return
        rows = database.all_users()
        await services.safe_edit(call.message, texts.admin_users(rows), reply_markup=kb.admin_panel(
            database.operators_state(config.OPERATORS)))
        await call.answer()

    @router.message(cmd("users"))
    async def users_cmd(message: Message) -> None:
        await message.answer(texts.admin_users(database.all_users()), parse_mode=config.PARSE_MODE)

    @router.message(cmd("panel"))
    async def panel_cmd(message: Message) -> None:
        await show_panel(message)

    # --- заказы -----------------------------------------------------------

    @router.message(cmd("ok"))
    async def order_ok(message: Message) -> None:
        match = CMD_RE.match(message.text or "")
        if not match or match.group(2) is None:
            await message.answer("Формат: <code>/ok_ID</code>", parse_mode=config.PARSE_MODE)
            return
        order_id = int(match.group(2))
        order = database.get_order(order_id)
        if order is None:
            await message.answer(f"⚠️ Заказ #{order_id} не найден")
            return
        bonus = texts.rank_bonus_cents(database.user_stats(int(order["user_id"]))["success"])
        applied, amount, user_id = database.complete_order(order_id, bonus)
        if not applied:
            await message.answer(f"ℹ️ Заказ #{order_id} уже завершён — повторно ничего не начислено.")
            return
        await message.answer(
            f"✅ Заказ #{order_id} засчитан: {texts.money(amount)} начислено "
            f"пользователю <code>{user_id}</code>.",
            parse_mode=config.PARSE_MODE,
        )
        try:
            await message.bot.send_message(
                user_id,
                f"✅ <b>Заказ #{order_id} засчитан</b>\n\n"
                f"Начислено: <b>{texts.money(amount)}</b>\n"
                f"Баланс уже в профиле.",
                parse_mode=config.PARSE_MODE,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("не смог уведомить %s: %s", user_id, exc)

    @router.message(cmd("progress"))
    async def order_progress(message: Message) -> None:
        match = CMD_RE.match(message.text or "")
        if not match or match.group(2) is None:
            await message.answer("Формат: <code>/progress_ID</code>", parse_mode=config.PARSE_MODE)
            return
        order_id = int(match.group(2))
        order = database.get_order(order_id)
        if order is None:
            await message.answer(f"⚠️ Заказ #{order_id} не найден")
            return
        if order["status"] in (db_module.ORDER_SUCCESS, db_module.ORDER_FAILED):
            await message.answer(f"ℹ️ Заказ #{order_id} уже завершён ({order['status']}).")
            return
        database.order_to_in_progress(order_id)
        await message.answer(f"⏳ Заказ #{order_id} взят в работу.")
        try:
            await message.bot.send_message(
                int(order["user_id"]),
                f"⏳ <b>Заказ #{order_id} взят в работу</b>",
                parse_mode=config.PARSE_MODE,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("не смог уведомить %s: %s", order["user_id"], exc)

    @router.message(cmd("no"))
    async def order_no(message: Message, state: FSMContext) -> None:
        match = CMD_RE.match(message.text or "")
        if not match or match.group(2) is None:
            await message.answer("Формат: <code>/no_ID причина</code>", parse_mode=config.PARSE_MODE)
            return
        order_id = int(match.group(2))
        reason = (match.group(3) or "").strip()
        order = database.get_order(order_id)
        if order is None:
            await message.answer(f"⚠️ Заказ #{order_id} не найден")
            return
        if not reason:
            await state.set_state(Admin.waiting_for_fail_reason)
            await state.update_data(order_id=order_id)
            await message.answer(
                f"✍️ Укажи причину отказа для заказа #{order_id} одним сообщением.",
                parse_mode=config.PARSE_MODE,
            )
            return
        await fail_order(message, order_id, reason)

    async def fail_order(message: Message, order_id: int, reason: str) -> None:
        applied, user_id = database.fail_order(order_id, reason)
        if not applied:
            await message.answer(f"ℹ️ Заказ #{order_id} уже завершён — статус не изменён.")
            return
        await message.answer(f"⛔ Заказ #{order_id} отклонён.")
        if user_id is not None and user_id != message.chat.id:
            try:
                await message.bot.send_message(
                    user_id,
                    f"⛔ <b>Заказ #{order_id} отклонён</b>\n\n"
                    f"Причина: <i>{reason}</i>",
                    parse_mode=config.PARSE_MODE,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("не смог уведомить %s: %s", user_id, exc)

    @router.message(Admin.waiting_for_fail_reason, F.text)
    async def fail_reason_input(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        order_id = data.get("order_id")
        await state.clear()
        if not order_id:
            await message.answer("⚠️ Заказ не выбран. Начни с /no_ID")
            return
        await fail_order(message, int(order_id), (message.text or "").strip()[:500])

    # --- выплаты ----------------------------------------------------------

    @router.message(cmd("yes"))
    async def approve_payout(message: Message) -> None:
        match = CMD_RE.match(message.text or "")
        if not match or match.group(2) is None:
            await message.answer("Формат: <code>/yes_ID_заявки</code>", parse_mode=config.PARSE_MODE)
            return
        wid = int(match.group(2))
        applied, user_id, amount = database.confirm_withdrawal(wid)
        if not applied:
            await message.answer(f"ℹ️ Заявка #{wid} уже обработана — повторного списания не будет.")
            return
        await message.answer(f"💸 Заявка #{wid} подтверждена, списано {texts.money(amount)}.")
        if user_id is not None and user_id != message.chat.id:
            try:
                await message.bot.send_message(
                    user_id,
                    f"💸 <b>Выплата #{wid} подтверждена</b>\n\n"
                    f"Сумма: <b>{texts.money(amount)}</b>",
                    parse_mode=config.PARSE_MODE,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("не смог уведомить %s: %s", user_id, exc)

    @router.message(cmd("reject"))
    async def reject_payout(message: Message) -> None:
        match = CMD_RE.match(message.text or "")
        if not match or match.group(2) is None:
            await message.answer("Формат: <code>/reject_ID</code>", parse_mode=config.PARSE_MODE)
            return
        wid = int(match.group(2))
        applied, user_id, amount = database.reject_withdrawal(wid)
        if not applied:
            await message.answer(f"ℹ️ Заявка #{wid} уже обработана.")
            return
        await message.answer(f"↩️ Заявка #{wid} отклонена, {texts.money(amount)} возвращены на баланс.")
        if user_id is not None and user_id != message.chat.id:
            try:
                await message.bot.send_message(
                    user_id,
                    f"↩️ <b>Заявка #{wid} отклонена</b>\n\n"
                    f"{texts.money(amount)} снова доступны к выводу.",
                    parse_mode=config.PARSE_MODE,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("не смог уведомить %s: %s", user_id, exc)

    # --- тикеты -----------------------------------------------------------

    @router.message(cmd("reply"))
    async def reply_ticket(message: Message, state: FSMContext) -> None:
        match = CMD_RE.match(message.text or "")
        if not match or match.group(2) is None:
            await message.answer("Формат: <code>/reply_ID текст</code>", parse_mode=config.PARSE_MODE)
            return
        ticket_id = int(match.group(2))
        text = (match.group(3) or "").strip()
        ticket = database.get_ticket(ticket_id)
        if ticket is None:
            await message.answer(f"⚠️ Обращение #{ticket_id} не найдено")
            return
        if not text:
            await state.set_state(Admin.waiting_for_admin_reply)
            await state.update_data(ticket_id=ticket_id)
            await message.answer(f"✍️ Отправь ответ для обращения #{ticket_id} одним сообщением.")
            return
        await send_ticket_reply(message, int(ticket["user_id"]), ticket_id, text)

    async def send_ticket_reply(message: Message, user_id: int, ticket_id: int, text: str) -> None:
        try:
            await message.bot.send_message(
                user_id,
                f"🆘 <b>Ответ поддержки</b> (обращение #{ticket_id})\n\n{text}",
                parse_mode=config.PARSE_MODE,
            )
        except Exception as exc:  # noqa: BLE001
            await message.answer(f"⚠️ Не смог доставить ответ: {exc}")
            return
        database.close_ticket(ticket_id)
        await message.answer(f"✅ Ответ по обращению #{ticket_id} доставлен.")

    @router.message(Admin.waiting_for_admin_reply, F.text)
    async def ticket_reply_input(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        ticket_id = data.get("ticket_id")
        text = (message.text or "").strip()
        if not ticket_id or not text:
            await state.clear()
            await message.answer("⚠️ Ответ не отправлен. Начни с /reply_ID")
            return
        ticket = database.get_ticket(int(ticket_id))
        await state.clear()
        if ticket is None:
            await message.answer(f"⚠️ Обращение #{ticket_id} не найдено")
            return
        await send_ticket_reply(message, int(ticket["user_id"]), int(ticket_id), text)

    # --- пользователи -----------------------------------------------------

    @router.message(cmd("approve"))
    async def approve_user(message: Message) -> None:
        match = CMD_RE.match(message.text or "")
        if not match or match.group(2) is None:
            await message.answer("Формат: <code>/approve_ID</code>", parse_mode=config.PARSE_MODE)
            return
        user_id = int(match.group(2))
        if database.get_user(user_id) is None:
            database.create_user(user_id, None)
        database.set_status(user_id, db_module.USER_ACTIVE)
        await message.answer(f"✅ Пользователь <code>{user_id}</code> одобрен.", parse_mode=config.PARSE_MODE)
        try:
            await message.bot.send_message(
                user_id,
                "✅ <b>Доступ открыт</b>\n\nЖми /start — кабинет ждёт. Your business. Your rules.",
                reply_markup=kb.main_reply(is_admin=(user_id == config.ADMIN_ID)),
                parse_mode=config.PARSE_MODE,
            )
        except Exception as exc:  # noqa: BLE001
            await message.answer(f"⚠️ Уведомление не доставлено: {exc}")

    @router.message(cmd("ban"))
    async def ban_user(message: Message) -> None:
        match = CMD_RE.match(message.text or "")
        if not match or match.group(2) is None:
            await message.answer("Формат: <code>/ban_ID</code>", parse_mode=config.PARSE_MODE)
            return
        user_id = int(match.group(2))
        if not database.set_status(user_id, db_module.USER_BANNED):
            await message.answer(f"⚠️ Пользователь <code>{user_id}</code> не найден.", parse_mode=config.PARSE_MODE)
            return
        await message.answer(f"🚫 Пользователь <code>{user_id}</code> забанен.", parse_mode=config.PARSE_MODE)
        try:
            await message.bot.send_message(user_id, texts.banned(), parse_mode=config.PARSE_MODE)
        except Exception:  # noqa: BLE001
            pass

    return router
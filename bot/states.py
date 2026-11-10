"""FSM-состояния Saul Goodman ⚖️.

Каждый сценарий имеет собственное состояние, после завершения — state.clear().
"""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Deal(StatesGroup):
    waiting_for_qr = State()


class Withdraw(StatesGroup):
    waiting_for_withdraw_wallet = State()


class Support(StatesGroup):
    waiting_for_support_msg = State()


class Admin(StatesGroup):
    waiting_for_admin_reply = State()  # ответ на тикет: /reply_ID
    waiting_for_fail_reason = State()  # причина отказа: /no_ID
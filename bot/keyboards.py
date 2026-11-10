"""Клавиатуры Saul Goodman ⚖️."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

import config

BTN_DEAL = "⚖️ Начать сделку"
BTN_PROFILE = "💼 Профиль"
BTN_STATS = "📊 Статистика"
BTN_SUPPORT = "🆘 Поддержка"
BTN_ADMIN = "⚙️ Админ-панель"


def main_reply(is_admin: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=BTN_DEAL))
    builder.row(KeyboardButton(text=BTN_PROFILE), KeyboardButton(text=BTN_STATS))
    builder.row(KeyboardButton(text=BTN_SUPPORT))
    if is_admin:
        builder.row(KeyboardButton(text=BTN_ADMIN))
    return builder.as_markup(resize_keyboard=True, input_field_placeholder="Your business. Your rules.")


def subscription() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📣 Вступить", url=config.CHANNEL_LINK))
    builder.row(InlineKeyboardButton(text="🔄 Проверить", callback_data="check_sub"))
    return builder.as_markup()


def operators(operators: list[tuple[str, bool, int]]) -> InlineKeyboardMarkup:
    """operators: [(название, открыт, цена_в_центах)] — две колонки."""
    builder = InlineKeyboardBuilder()
    for name, is_open, price_cents in operators:
        mark = "🟢" if is_open else "🔴"
        price = f"${price_cents / 100:.2f}"
        builder.button(
            text=f"{mark} {name} · {price}",
            callback_data=f"op:{name}" if is_open else "op_closed",
        )
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="back_menu"))
    return builder.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="back_menu"))
    return builder.as_markup()


def profile_actions() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Вывести", callback_data="withdraw")
    builder.button(text="🔄 Обновить", callback_data="refresh_profile")
    builder.adjust(2)
    return builder.as_markup()


def cancel() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel_fsm"))
    return builder.as_markup()


def admin_panel(operators_state: dict[str, bool]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for name, is_open in operators_state.items():
        mark = "🟢" if is_open else "🔴"
        action = "close" if is_open else "open"
        builder.button(text=f"{mark} {name}", callback_data=f"adm:op:{action}:{name}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users"))
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="adm:refresh"))
    return builder.as_markup()
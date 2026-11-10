"""Вспомогательные сервисы Saul Goodman ⚖️."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

import config

log = logging.getLogger("saul")


async def safe_edit(message: Message, text: str, reply_markup=None) -> None:
    """Правка сообщения без ошибки ``message is not modified``.

    Если Telegram говорит, что текст не изменился, — молча выходим;
    если правка невозможна (например, сообщение слишком старое) — шлём новое.
    """
    if message.text == text and reply_markup is None:
        return
    try:
        if message.text == text:
            await message.edit_reply_markup(reply_markup=reply_markup)
        else:
            await message.edit_text(text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)
    except TelegramBadRequest as exc:
        detail = str(exc).lower()
        if "message is not modified" in detail:
            return
        try:
            await message.answer(text, reply_markup=reply_markup, parse_mode=config.PARSE_MODE)
        except TelegramBadRequest:
            log.warning("edit failed: %s", exc)


async def notify_admin(bot: Bot, text: str, **kwargs: Any) -> bool:
    if not config.ADMIN_ID:
        log.warning("ADMIN_ID не задан — уведомление не отправлено")
        return False
    try:
        await bot.send_message(config.ADMIN_ID, text, parse_mode=config.PARSE_MODE, **kwargs)
        return True
    except Exception as exc:  # noqa: BLE001 — админ мог не нажать /start
        log.warning("не удалось уведомить админа: %s", exc)
        return False


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """Проверка подписки на канал. Если канал не настроен — доступ открыт.

    Бот должен быть администратором канала, иначе Telegram отвечает ошибкой;
    в этом случае мы не запираем пользователей в бесконечной проверке.
    """
    if not config.CHANNEL_ID:
        return True
    try:
        member = await bot.get_chat_member(config.CHANNEL_ID, user_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("проверка подписки недоступна: %s", exc)
        return True
    return member.status not in {"left", "kicked"}
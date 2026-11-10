"""Фильтры доступа Saul Goodman ⚖️."""
from __future__ import annotations

import re
from typing import Any

from aiogram.filters import BaseFilter
from aiogram.types import Message

import config
from bot import db as db_module


class IsAdmin(BaseFilter):
    """Только ADMIN_ID и только в личном чате.

    Скрытая кнопка — не безопасность: фильтр проверяет ID на каждом обработчике.
    """

    async def __call__(self, message: Message) -> bool:
        user = message.from_user
        return (
            message.chat.type == "private"
            and user is not None
            and config.ADMIN_ID != 0
            and user.id == config.ADMIN_ID
        )


class AdminCommand(BaseFilter):
    """Ловит и ``/ok``, и ``/ok_12`` — стандартный Command берёт только первое слово."""

    def __init__(self, name: str) -> None:
        self.name = name.lower()
        self.pattern = re.compile(rf"^/{re.escape(self.name)}(?:_\d+)?(?:\s|$)", re.IGNORECASE)

    async def __call__(self, message: Message) -> bool:
        return bool(message.text and self.pattern.match(message.text))


def cmd(name: str) -> AdminCommand:
    return AdminCommand(name)


def make_active_filter(database: db_module.Database) -> BaseFilter:
    """Пропускает только пользователей со статусом active."""

    class IsActive(BaseFilter):
        async def __call__(self, message: Message) -> bool:
            if message.from_user is None:
                return False
            user = database.get_user(message.from_user.id)
            return user is not None and user["status"] == db_module.USER_ACTIVE

    return IsActive()
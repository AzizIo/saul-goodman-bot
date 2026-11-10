"""Saul Goodman ⚖️ — точка входа.

Запуск: ``python main.py`` (или через Docker / systemd, см. README).
"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

import config
from bot import db as db_module
from bot.handlers import build_router

log = logging.getLogger("saul")


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    # aiogram болтлив на INFO — оставим ему WARNING
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def cleanup_loop(database: db_module.Database) -> None:
    """Суточная гигиена: QR-секреты не хранятся дольше QR_RETENTION_DAYS."""
    while True:
        try:
            removed = database.cleanup_old_orders(config.QR_RETENTION_DAYS)
            if removed:
                log.info("очищены file_id у %s старых заказов", removed)
        except Exception as exc:  # noqa: BLE001
            log.warning("ошибка очистки: %s", exc)
        await asyncio.sleep(24 * 60 * 60)


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть кабинет"),
            BotCommand(command="help", description="Как это работает"),
            BotCommand(command="id", description="Мой Telegram ID"),
        ]
    )


async def main() -> None:
    setup_logging()

    if not config.BOT_TOKEN:
        log.error("BOT_TOKEN не задан — заполни .env (см. .env.example)")
        raise SystemExit(1)
    if not config.ADMIN_ID:
        log.warning("ADMIN_ID не задан: админ-команды будут недоступны")

    database = db_module.Database(config.DB_PATH)
    database.init()
    database.seed_operators(config.OPERATORS)
    log.info("база готова: %s", database.path)

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(build_router(database))

    # сначала рукопожатие: неверный токен или закрытая сеть видны сразу,
    # а не после пяти попыток автоперезапуска под systemd
    try:
        me = await bot.get_me()
    except Exception as exc:  # noqa: BLE001 — токен или сеть
        log.error("не удалось связаться с Telegram: %s", exc)
        log.error("проверь BOT_TOKEN и доступ в сеть (api.telegram.org:443)")
        await bot.session.close()
        raise SystemExit(1)

    await set_commands(bot)
    cleaner = asyncio.create_task(cleanup_loop(database))
    log.info("запущен %s (@%s)", config.BRAND, me.username)

    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        cleaner.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("остановлен")
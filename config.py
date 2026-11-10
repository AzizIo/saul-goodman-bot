"""Конфигурация проекта Saul Goodman ⚖️.

Секреты (токен, ID канала, админ) читаются из окружения или файла ``.env``
и никогда не попадают в репозиторий.

Все денежные величины хранятся в целых минимальных единицах (центах):
никакой бинарной арифметики с плавающей точкой на пути к балансу.
"""
from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv не обязателен для тестов
        return
    load_dotenv(BASE_DIR / ".env")


_load_env()


def _str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _int(name: str, default: int = 0) -> int:
    raw = _str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    raw = _str(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "да"}


def _chat_id(raw: str) -> int | str:
    """CHANNEL_ID может быть числом (-100...) или @username."""
    raw = raw.strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return raw if raw.startswith("@") else f"@{raw.lstrip('@')}"


# --- Основные настройки -----------------------------------------------------

BOT_TOKEN: str = _str("BOT_TOKEN")
ADMIN_ID: int = _int("ADMIN_ID")
CHANNEL_ID: int | str = _chat_id(_str("CHANNEL_ID", "0"))
CHANNEL_LINK: str = _str("CHANNEL_LINK", "https://t.me/")
CHANNEL_TITLE: str = _str("CHANNEL_TITLE", "наш канал")

PARSE_MODE = "HTML"
CURRENCY = "$"
BRAND = "Saul Goodman"

# Минимальная сумма к выводу (в долларах).
MIN_WITHDRAWAL = Decimal(_str("MIN_WITHDRAWAL", "1.00"))

# --- Инфраструктура ---------------------------------------------------------

DB_PATH = Path(_str("DB_PATH", str(BASE_DIR / "data" / "saul.db")))
QR_DIR = Path(_str("QR_DIR", str(BASE_DIR / "data" / "qr")))
# Скачивать ли сами файлы QR на диск. По умолчанию выключено: бот работает
# с file_id Telegram и не хранит секреты активации на сервере.
QR_STORE_FILES = _bool("QR_STORE_FILES", False)
QR_RETENTION_DAYS = _int("QR_RETENTION_DAYS", 7)
LOG_LEVEL = _str("LOG_LEVEL", "INFO")

# --- Деньги -----------------------------------------------------------------

CENTS = Decimal("0.01")


def to_cents(amount: Decimal | str | int | float) -> int:
    """$1.5 -> 150. Округление половины вверх, без float на выходе."""
    return int((Decimal(str(amount)) / CENTS).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# --- Операторы --------------------------------------------------------------
# Приём по оператору можно открыть/закрыть в админ-панели; состояние
# сохраняется в БД и переживает перезапуск бота.

OPERATORS: dict[str, dict] = {
    "Beeline": {"price": Decimal("1.50"), "open": True},
    "MTS": {"price": Decimal("1.60"), "open": True},
    "MegaFon": {"price": Decimal("1.70"), "open": True},
    "Tele2": {"price": Decimal("1.40"), "open": True},
    "Yota": {"price": Decimal("1.30"), "open": False},
}

# --- Ранги ------------------------------------------------------------------
# Порог — количество успешных сдач, бонус прибавляется к цене оператора.

RANKS: list[dict] = [
    {"name": "Новичок", "threshold": 0, "bonus": Decimal("0.00")},
    {"name": "Параллегал", "threshold": 10, "bonus": Decimal("0.10")},
    {"name": "Адвокат", "threshold": 50, "bonus": Decimal("0.25")},
    {"name": "Партнёр", "threshold": 150, "bonus": Decimal("0.50")},
    {"name": "Дон", "threshold": 400, "bonus": Decimal("1.00")},
]

RANK_LEVELS: list[dict] = [
    {"name": rank["name"], "threshold": int(rank["threshold"]), "bonus_cents": to_cents(rank["bonus"])}
    for rank in RANKS
]


def operator_price_cents(name: str) -> int:
    meta = OPERATORS.get(name)
    return to_cents(meta["price"]) if meta else 0
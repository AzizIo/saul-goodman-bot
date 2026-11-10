from decimal import Decimal

import config
from bot import texts
from bot.validators import normalize_phone, parse_wallet


def test_to_cents_is_exact():
    assert config.to_cents("1.50") == 150
    assert config.to_cents(Decimal("0.01")) == 1
    assert config.to_cents("0.005") == 1  # половина — вверх
    assert config.to_cents(2) == 200


def test_money_format():
    assert texts.money(150) == "$1.50"
    assert texts.money(0) == "$0.00"
    assert texts.money(-250) == "$-2.50"


def test_progress_bar():
    assert texts.progress_bar(0, 10) == "⬜" * 10
    assert texts.progress_bar(5, 10) == "🟩" * 5 + "⬜" * 5
    assert texts.progress_bar(20, 10) == "🟩" * 10
    assert texts.progress_bar(3, 0) == "🟩" * 10


def test_ranks():
    assert texts.rank_for(0)["name"] == "Новичок"
    assert texts.rank_for(10)["name"] == "Параллегал"
    assert texts.next_rank(0)["threshold"] == 10
    assert texts.next_rank(10_000) is None


def test_phone_validation():
    assert normalize_phone("+7 900 123-45-67") == "+79001234567"
    assert normalize_phone("79001234567") == "79001234567"
    assert normalize_phone("беру, +79001234567, готово") == "+79001234567"
    assert normalize_phone("без номера") is None
    assert normalize_phone("123") is None
    assert normalize_phone("") is None


def test_wallet_validation():
    bep = "0x" + "a" * 40
    trc = "T" + "1" * 33
    assert parse_wallet(bep) == ("USDT BEP20", bep)
    assert parse_wallet(f"USDT BEP20 {bep}") == ("USDT BEP20", bep)
    assert parse_wallet(trc) == ("USDT TRC20", trc)
    assert parse_wallet(f"usdt trc20 {trc}") == ("USDT TRC20", trc)
    assert parse_wallet("привет") is None
    assert parse_wallet("0x123") is None
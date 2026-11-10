import config
from bot.db import Database, USER_ACTIVE, USER_BANNED, USER_PENDING
from bot.filters import AdminCommand


def test_new_user_is_pending(database):
    assert database.create_user(1, "u1") is True
    user = database.get_user(1)
    assert user["status"] == USER_PENDING
    assert user["balance"] == 0


def test_duplicate_registration(database):
    database.create_user(1, "u1")
    assert database.create_user(1, "u1") is False


def test_status_transitions(database):
    database.create_user(1, "u1")
    assert database.set_status(1, USER_ACTIVE) is True
    assert database.get_user(1)["status"] == USER_ACTIVE
    assert database.set_status(1, USER_BANNED) is True
    assert database.get_user(1)["status"] == USER_BANNED


def test_invalid_status_rejected(database):
    database.create_user(1, "u1")
    try:
        database.set_status(1, "hacker")
    except ValueError:
        return
    raise AssertionError("недопустимый статус должен бросать ValueError")


def test_set_status_unknown_user(database):
    assert database.set_status(999, USER_ACTIVE) is False


def test_operator_state_persists(database):
    assert database.operators_state(config.OPERATORS)["Beeline"] is True
    database.set_operator_open("Beeline", False)
    assert database.operators_state(config.OPERATORS)["Beeline"] is False
    # повторная инициализация не сбрасывает состояние
    database.seed_operators(config.OPERATORS)
    assert database.operators_state(config.OPERATORS)["Beeline"] is False


def test_db_survives_reopen(tmp_path):
    first = Database(tmp_path / "persist.db")
    first.init()
    first.create_user(7, "seven")
    first.set_operator_open("MTS", False)

    second = Database(tmp_path / "persist.db")
    second.init()
    assert second.get_user(7)["id"] == 7
    assert second.operators_state(config.OPERATORS)["MTS"] is False


def test_admin_command_filter_matches_both_forms():
    class Msg:
        def __init__(self, text):
            self.text = text

    import asyncio

    filt = AdminCommand("ok")
    assert asyncio.run(filt(Msg("/ok_12"))) is True
    assert asyncio.run(filt(Msg("/ok 12"))) is True
    assert asyncio.run(filt(Msg("/ok"))) is True
    assert asyncio.run(filt(Msg("/ok_12x"))) is False
    assert asyncio.run(filt(Msg("/okay"))) is False
from bot.db import TX_EARNING


def _fund(database, user_id, cents):
    oid = database.create_order(user_id, "Beeline", cents, "+79001234567", None)
    database.complete_order(oid)


def test_withdrawal_reserves_funds(database, active_user):
    _fund(database, active_user, 500)
    wid = database.create_withdrawal(active_user, 300, "T" + "1" * 33, "USDT TRC20")
    assert wid is not None

    user = database.get_user(active_user)
    assert user["balance"] == 500        # общий баланс ещё не тронут
    assert user["available"] == 200      # сумма зарезервирована

    order = database.get_withdrawal(wid)
    assert order["amount"] == 300
    assert order["status"] == "pending"


def test_withdrawal_insufficient(database, active_user):
    _fund(database, active_user, 100)
    assert database.create_withdrawal(active_user, 300, "T" + "1" * 33, "USDT TRC20") is None
    assert database.get_user(active_user)["available"] == 100


def test_withdraw_is_idempotent(database, active_user):
    _fund(database, active_user, 500)
    wid = database.create_withdrawal(active_user, 300, "T" + "1" * 33, "USDT TRC20")

    applied, user_id, amount = database.confirm_withdrawal(wid)
    assert applied is True and amount == 300 and user_id == active_user
    user = database.get_user(active_user)
    assert user["balance"] == 200
    assert user["available"] == 200

    # повторное подтверждение не списывает ещё раз
    again, _, _ = database.confirm_withdrawal(wid)
    assert again is False
    assert database.get_user(active_user)["balance"] == 200


def test_confirm_uses_reserved_amount(database, active_user):
    _fund(database, active_user, 500)
    wid = database.create_withdrawal(active_user, 200, "T" + "1" * 33, "USDT TRC20")
    _fund(database, active_user, 100)  # баланс вырос уже после создания заявки
    assert database.get_user(active_user)["available"] == 400

    database.confirm_withdrawal(wid)
    user = database.get_user(active_user)
    assert user["balance"] == 400
    assert user["available"] == 400


def test_reject_returns_funds_once(database, active_user):
    _fund(database, active_user, 500)
    wid = database.create_withdrawal(active_user, 300, "T" + "1" * 33, "USDT TRC20")

    applied, _, amount = database.reject_withdrawal(wid)
    assert applied is True and amount == 300
    assert database.get_user(active_user)["available"] == 500
    assert database.get_user(active_user)["balance"] == 500

    again, _, _ = database.reject_withdrawal(wid)
    assert again is False
    assert database.get_user(active_user)["available"] == 500


def test_rejected_withdrawal_cannot_be_confirmed(database, active_user):
    _fund(database, active_user, 500)
    wid = database.create_withdrawal(active_user, 300, "T" + "1" * 33, "USDT TRC20")
    database.reject_withdrawal(wid)
    applied, _, _ = database.confirm_withdrawal(wid)
    assert applied is False
    assert database.get_user(active_user)["balance"] == 500


def test_two_withdrawals_sequentially(database, active_user):
    _fund(database, active_user, 500)
    first = database.create_withdrawal(active_user, 200, "T" + "1" * 33, "USDT TRC20")
    second = database.create_withdrawal(active_user, 300, "0x" + "a" * 40, "USDT BEP20")
    assert first and second
    assert database.get_user(active_user)["available"] == 0
    assert database.create_withdrawal(active_user, 100, "T" + "1" * 33, "USDT TRC20") is None

    database.confirm_withdrawal(first)
    database.confirm_withdrawal(second)
    assert database.get_user(active_user)["balance"] == 0


def test_transaction_journal(database, active_user):
    _fund(database, active_user, 500)
    wid = database.create_withdrawal(active_user, 300, "T" + "1" * 33, "USDT TRC20")
    database.confirm_withdrawal(wid)
    with database.connect() as conn:
        kinds = [row["kind"] for row in conn.execute(
            "SELECT kind FROM transactions WHERE user_id = ? ORDER BY id", (active_user,))]
        total = conn.execute(
            "SELECT SUM(amount) FROM transactions WHERE user_id = ?", (active_user,)).fetchone()[0]
    assert kinds == [TX_EARNING, "withdraw_paid"]
    assert total == database.get_user(active_user)["balance"]


def test_duplicate_earning_blocked_by_unique_index(database, active_user):
    import sqlite3

    oid = database.create_order(active_user, "Beeline", 150, "+79001234567", None)
    database.complete_order(oid)
    try:
        with database.tx() as conn:
            conn.execute(
                "INSERT INTO transactions (user_id, amount, kind, ref_type, ref_id, comment, created_at)"
                " VALUES (?, ?, 'earning', 'order', ?, 'dup', 'now')",
                (active_user, 150, oid),
            )
    except sqlite3.IntegrityError:
        return
    raise AssertionError("журнал должен запрещать повторное начисление по заказу")
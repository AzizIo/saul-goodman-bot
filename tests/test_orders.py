from bot.db import (
    ORDER_FAILED,
    ORDER_IN_PROGRESS,
    ORDER_PENDING,
    ORDER_SUCCESS,
    TX_EARNING,
)


def _order(database, user_id=500, price=150, phone="+79001234567"):
    return database.create_order(user_id, "Beeline", price, phone, "file-1")


def test_create_order(database, active_user):
    oid = _order(database)
    order = database.get_order(oid)
    assert order["status"] == ORDER_PENDING
    assert order["price"] == 150
    assert order["phone"] == "+79001234567"


def test_complete_order_credits_once(database, active_user):
    oid = _order(database)
    applied, amount, user_id = database.complete_order(oid, bonus_cents=10)
    assert applied is True
    assert amount == 160
    assert user_id == active_user
    assert database.get_order(oid)["status"] == ORDER_SUCCESS

    user = database.get_user(active_user)
    assert user["balance"] == 160
    assert user["available"] == 160

    # повторное /ok денег не добавляет
    second, second_amount, _ = database.complete_order(oid, bonus_cents=10)
    assert second is False
    assert second_amount == 0
    assert database.get_user(active_user)["balance"] == 160


def test_complete_from_in_progress(database, active_user):
    oid = _order(database)
    database.order_to_in_progress(oid)
    assert database.get_order(oid)["status"] == ORDER_IN_PROGRESS
    applied, amount, _ = database.complete_order(oid)
    assert applied is True
    assert amount == 150


def test_progress_keeps_status(database, active_user):
    oid = _order(database)
    assert database.order_to_in_progress(oid) is True
    assert database.order_to_in_progress(oid) is True
    assert database.get_order(oid)["status"] == ORDER_IN_PROGRESS


def test_fail_order(database, active_user):
    oid = _order(database)
    applied, user_id = database.fail_order(oid, "битый QR")
    assert applied is True
    assert user_id == active_user
    order = database.get_order(oid)
    assert order["status"] == ORDER_FAILED
    assert order["fail_reason"] == "битый QR"
    assert database.get_user(active_user)["balance"] == 0

    # повторный отказ ничего не меняет
    again, _ = database.fail_order(oid, "другая причина")
    assert again is False
    assert database.get_order(oid)["fail_reason"] == "битый QR"


def test_cannot_fail_completed_order(database, active_user):
    oid = _order(database)
    database.complete_order(oid)
    applied, _ = database.fail_order(oid, "поздно")
    assert applied is False
    assert database.get_order(oid)["status"] == ORDER_SUCCESS
    assert database.get_user(active_user)["balance"] == 150


def test_cannot_complete_failed_order(database, active_user):
    oid = _order(database)
    database.fail_order(oid, "брак")
    applied, amount, _ = database.complete_order(oid)
    assert applied is False
    assert amount == 0
    assert database.get_user(active_user)["balance"] == 0


def test_unknown_order(database, active_user):
    applied, amount, user_id = database.complete_order(999, 0)
    assert (applied, amount, user_id) == (False, 0, None)
    applied, user_id = database.fail_order(999, "нет")
    assert (applied, user_id) == (False, None)


def test_journal_explains_balance(database, active_user):
    for _ in range(3):
        database.complete_order(_order(database))
    stats = database.user_stats(active_user)
    assert stats["success"] == 3
    assert stats["earned"] == 450
    user = database.get_user(active_user)
    assert user["balance"] == stats["earned"]


def test_stats_last_24h_and_operators(database, active_user):
    oid = _order(database, price=150)
    database.complete_order(oid)
    database.create_order(active_user, "MTS", 160, "+79001112233", "f2")
    database.create_order(active_user, "Beeline", 150, "+79001112244", "f3")

    stats = database.stats_last_24h(active_user)
    assert stats["total"] == 3
    assert stats["success"] == 1
    assert stats["pending"] == 2

    rows = {row["operator"]: row for row in database.operator_stats(active_user)}
    assert rows["Beeline"]["s"] == 1
    assert rows["Beeline"]["total"] == 2


def test_old_orders_excluded_from_24h(database, active_user):
    oid = _order(database)
    with database.tx() as conn:
        conn.execute("UPDATE orders SET created_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (oid,))
    assert database.stats_last_24h(active_user)["total"] == 0
    assert database.user_stats(active_user)["total"] == 1


def test_cleanup_releases_qr(tmp_path):
    from bot.db import Database

    db = Database(tmp_path / "c.db")
    db.init()
    db.create_user(1, None)

    fresh = db.create_order(1, "Beeline", 150, "+79001234567", "secret-file")
    stale = db.create_order(1, "Beeline", 150, "+79001112233", "secret-file-2")
    db.set_order_qr_path(stale, str(tmp_path / "qr-order.jpg"))

    assert db.cleanup_old_orders(7) == []  # свежий заказ не трогаем

    with db.tx() as conn:
        conn.execute("UPDATE orders SET created_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (stale,))

    paths = db.cleanup_old_orders(7)
    assert paths == [str(tmp_path / "qr-order.jpg")]
    assert db.get_order(stale)["file_id"] is None
    assert db.get_order(stale)["qr_path"] is None
    assert db.get_order(fresh)["file_id"] == "secret-file"


def test_qr_files_removed_from_disk(tmp_path, monkeypatch):
    import config
    from bot import services

    monkeypatch.setattr(config, "QR_STORE_FILES", True)
    monkeypatch.setattr(config, "QR_DIR", tmp_path / "qr")

    qr = tmp_path / "qr" / "order-9.jpg"
    qr.parent.mkdir(parents=True)
    qr.write_bytes(b"jpeg")
    assert services.remove_qr_files([str(qr)]) == 1
    assert not qr.exists()
    assert services.remove_qr_files([str(qr)]) == 1  # повторно — не падает


def test_store_qr_disabled_by_default(monkeypatch):
    import config
    from bot import services
    import asyncio

    monkeypatch.setattr(config, "QR_STORE_FILES", False)
    # без сети и без записи на диск: выключенная настройка → None
    assert asyncio.run(services.store_qr_file(None, "file-id", 1)) is None

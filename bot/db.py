"""SQLite-слой Saul Goodman ⚖️.

Принципы:
* деньги — только целые центы (INTEGER), никаких REAL на пути к балансу;
* каждый переход статуса — атомарный (``UPDATE ... WHERE status IN (...)``),
  поэтому повторная команда администратора не начисляет и не списывает дважды;
* баланс всегда объясним через журнал ``transactions``;
* все запросы параметризованные, внешние ключи включены.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

USER_PENDING = "pending"
USER_ACTIVE = "active"
USER_BANNED = "banned"

ORDER_PENDING = "pending"
ORDER_IN_PROGRESS = "in_progress"
ORDER_SUCCESS = "success"
ORDER_FAILED = "failed"

WITHDRAW_PENDING = "pending"
WITHDRAW_PAID = "paid"
WITHDRAW_REJECTED = "rejected"

TX_EARNING = "earning"
TX_WITHDRAW_PAID = "withdraw_paid"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT,
    balance       INTEGER NOT NULL DEFAULT 0,
    available     INTEGER NOT NULL DEFAULT 0,
    reg_date      TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    operator    TEXT    NOT NULL,
    price       INTEGER NOT NULL,
    phone       TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    fail_reason TEXT,
    date        TEXT    NOT NULL,
    file_id     TEXT,
    qr_path     TEXT,
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_user   ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);

CREATE TABLE IF NOT EXISTS withdrawals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    amount     INTEGER NOT NULL,
    wallet     TEXT    NOT NULL,
    network    TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'pending',
    created_at TEXT    NOT NULL,
    settled_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_withdrawals_user ON withdrawals(user_id);

CREATE TABLE IF NOT EXISTS tickets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    message    TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'open',
    created_at TEXT    NOT NULL,
    answered_at TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    amount     INTEGER NOT NULL,
    kind       TEXT    NOT NULL,
    ref_type   TEXT,
    ref_id     INTEGER,
    comment    TEXT,
    created_at TEXT    NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_once
    ON transactions(user_id, kind, ref_type, ref_id)
    WHERE ref_type IS NOT NULL AND ref_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id);

CREATE TABLE IF NOT EXISTS operator_state (
    operator TEXT PRIMARY KEY,
    is_open  INTEGER NOT NULL DEFAULT 1
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _day_ago_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path = "data/saul.db") -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path_str = str(self.path)

    # --- соединение -------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path_str, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        if self.path_str != ":memory:":
            conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """Соединение, которое действительно закрывается (sqlite3 сам не умеет)."""
        with closing(self.connect()) as conn:
            yield conn

    @contextmanager
    def tx(self, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        """Транзакция: всё или ничего, включая финансовые операции."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def init(self) -> None:
        with self.session() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Догоняющие ALTER TABLE: база не должна требовать ручной правки."""
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
        if "qr_path" not in columns:
            conn.execute("ALTER TABLE orders ADD COLUMN qr_path TEXT")

    # --- пользователи -----------------------------------------------------

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        with self.session() as conn:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def create_user(self, user_id: int, username: str | None = None) -> bool:
        """True — пользователь создан впервые."""
        with self.tx() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO users (id, username, reg_date, status) VALUES (?, ?, ?, ?)",
                (user_id, username, now_iso(), USER_PENDING),
            )
            return cur.rowcount > 0

    def set_username(self, user_id: int, username: str | None) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))

    def set_status(self, user_id: int, status: str) -> bool:
        allowed = {USER_PENDING, USER_ACTIVE, USER_BANNED}
        if status not in allowed:
            raise ValueError(f"unknown status {status}")
        with self.tx() as conn:
            cur = conn.execute("UPDATE users SET status = ? WHERE id = ?", (status, user_id))
            return cur.rowcount > 0

    def all_users(self) -> list[sqlite3.Row]:
        with self.session() as conn:
            return conn.execute(
                "SELECT id, username, status, balance, available FROM users ORDER BY id"
            ).fetchall()

    def user_stats(self, user_id: int) -> dict[str, int]:
        with self.session() as conn:
            rows = conn.execute(
                """
                SELECT operator, status, COUNT(*) AS cnt
                FROM orders WHERE user_id = ? GROUP BY operator, status
                """,
                (user_id,),
            ).fetchall()
        stats: dict[str, int] = {
            "success": 0, "in_progress": 0, "failed": 0, "pending": 0,
            "total": 0, "earned": 0,
        }
        for row in rows:
            stats[row["status"]] = stats.get(row["status"], 0) + row["cnt"]
            stats["total"] += row["cnt"]
        with self.session() as conn:
            earned = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions "
                "WHERE user_id = ? AND kind = ?",
                (user_id, TX_EARNING),
            ).fetchone()[0]
        stats["earned"] = int(earned or 0)
        return stats

    def operator_stats(self, user_id: int) -> list[sqlite3.Row]:
        with self.session() as conn:
            return conn.execute(
                """
                SELECT operator,
                       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS s,
                       SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS p,
                       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS f,
                       COUNT(*) AS total
                FROM orders WHERE user_id = ?
                GROUP BY operator ORDER BY operator
                """,
                (user_id,),
            ).fetchall()

    # --- заказы -----------------------------------------------------------

    def create_order(
        self,
        user_id: int,
        operator: str,
        price_cents: int,
        phone: str,
        file_id: str | None,
        qr_path: str | None = None,
    ) -> int:
        with self.tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO orders
                    (user_id, operator, price, phone, status, date, file_id, qr_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, operator, price_cents, phone, ORDER_PENDING,
                 now_iso(), file_id, qr_path, now_iso()),
            )
            return int(cur.lastrowid)

    def set_order_qr_path(self, order_id: int, qr_path: str) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE orders SET qr_path = ? WHERE id = ?", (qr_path, order_id))

    def get_order(self, order_id: int) -> sqlite3.Row | None:
        with self.session() as conn:
            return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    def order_to_in_progress(self, order_id: int) -> bool:
        with self.tx() as conn:
            cur = conn.execute(
                "UPDATE orders SET status = ? WHERE id = ? AND status IN (?, ?)",
                (ORDER_IN_PROGRESS, order_id, ORDER_PENDING, ORDER_IN_PROGRESS),
            )
            # повторный /progress не меняет ничего, но и не считается ошибкой
            return cur.rowcount > 0 or self.get_order(order_id) is not None

    def complete_order(self, order_id: int, bonus_cents: int = 0) -> tuple[bool, int, int | None]:
        """Засчитать заказ. Возвращает (сработало, начислено, user_id).

        Начисление идёт в той же транзакции, что и смена статуса, и только
        если заказ ещё не завершён — повторный /ok денег не добавит.
        """
        with self.tx() as conn:
            order = conn.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None:
                return False, 0, None
            if order["status"] == ORDER_SUCCESS:
                return False, 0, int(order["user_id"])
            if order["status"] == ORDER_FAILED:
                return False, 0, int(order["user_id"])
            amount = int(order["price"]) + int(bonus_cents)
            cur = conn.execute(
                "UPDATE orders SET status = ? WHERE id = ? AND status IN (?, ?)",
                (ORDER_SUCCESS, order_id, ORDER_PENDING, ORDER_IN_PROGRESS),
            )
            if cur.rowcount == 0:
                return False, 0, int(order["user_id"])
            conn.execute(
                "UPDATE users SET balance = balance + ?, available = available + ? WHERE id = ?",
                (amount, amount, order["user_id"]),
            )
            conn.execute(
                """
                INSERT INTO transactions (user_id, amount, kind, ref_type, ref_id, comment, created_at)
                VALUES (?, ?, ?, 'order', ?, ?, ?)
                """,
                (order["user_id"], amount, TX_EARNING, order_id,
                 f"{order['operator']} #{order_id}", now_iso()),
            )
            return True, amount, int(order["user_id"])

    def fail_order(self, order_id: int, reason: str) -> tuple[bool, int | None]:
        with self.tx() as conn:
            order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if order is None:
                return False, None
            if order["status"] in (ORDER_FAILED, ORDER_SUCCESS):
                return False, int(order["user_id"])
            cur = conn.execute(
                "UPDATE orders SET status = ?, fail_reason = ? "
                "WHERE id = ? AND status IN (?, ?)",
                (ORDER_FAILED, reason, order_id, ORDER_PENDING, ORDER_IN_PROGRESS),
            )
            return cur.rowcount > 0, int(order["user_id"])

    def user_orders_today_count(self, user_id: int) -> int:
        with self.session() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM orders WHERE user_id = ? AND created_at >= ?",
                (user_id, _day_ago_iso()),
            ).fetchone()[0])

    # --- статистика -------------------------------------------------------

    def stats_last_24h(self, user_id: int) -> dict[str, int]:
        with self.session() as conn:
            row = conn.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success,
                  SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,
                  SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                  SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending
                FROM orders WHERE user_id = ? AND created_at >= ?
                """,
                (user_id, _day_ago_iso()),
            ).fetchone()
        return {k: int(row[k] or 0) for k in ("total", "success", "in_progress", "failed", "pending")}

    def fail_reasons(self, user_id: int, limit: int = 10) -> list[sqlite3.Row]:
        with self.session() as conn:
            return conn.execute(
                """
                SELECT operator, fail_reason, date FROM orders
                WHERE user_id = ? AND status = 'failed' AND fail_reason IS NOT NULL
                ORDER BY id DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

    def global_stats(self) -> dict[str, int]:
        with self.session() as conn:
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            pending_orders = conn.execute(
                "SELECT COUNT(*) FROM orders WHERE status IN ('pending','in_progress')"
            ).fetchone()[0]
            payouts = conn.execute(
                "SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'"
            ).fetchone()[0]
            tickets = conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE status = 'open'"
            ).fetchone()[0]
        return {
            "users": int(users), "orders": int(orders), "pending_orders": int(pending_orders),
            "payouts": int(payouts), "tickets": int(tickets),
        }

    # --- выплаты ----------------------------------------------------------

    def create_withdrawal(
        self, user_id: int, amount_cents: int, wallet: str, network: str
    ) -> int | None:
        """Резервирует сумму (available -= amount) и создаёт заявку.

        Возвращает id заявки либо None, если средств не хватает.
        """
        with self.tx() as conn:
            cur = conn.execute(
                "UPDATE users SET available = available - ? WHERE id = ? AND available >= ?",
                (amount_cents, user_id, amount_cents),
            )
            if cur.rowcount == 0:
                return None
            ins = conn.execute(
                """
                INSERT INTO withdrawals (user_id, amount, wallet, network, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, amount_cents, wallet, network, WITHDRAW_PENDING, now_iso()),
            )
            # резервирование не пишем в журнал: баланс пользователя не меняется,
            # в журнал попадает только фактическое списание при подтверждении
            return int(ins.lastrowid)

    def get_withdrawal(self, wid: int) -> sqlite3.Row | None:
        with self.session() as conn:
            return conn.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)).fetchone()

    def confirm_withdrawal(self, wid: int) -> tuple[bool, int | None, int]:
        """Подтверждение выплаты: списывает ровно зарезервированную сумму."""
        with self.tx() as conn:
            row = conn.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)).fetchone()
            if row is None:
                return False, None, 0
            if row["status"] != WITHDRAW_PENDING:
                return False, int(row["user_id"]), int(row["amount"])
            cur = conn.execute(
                "UPDATE withdrawals SET status = ?, settled_at = ? WHERE id = ? AND status = ?",
                (WITHDRAW_PAID, now_iso(), wid, WITHDRAW_PENDING),
            )
            if cur.rowcount == 0:
                return False, int(row["user_id"]), int(row["amount"])
            amount = int(row["amount"])
            conn.execute(
                "UPDATE users SET balance = balance - ? WHERE id = ?",
                (amount, row["user_id"]),
            )
            conn.execute(
                """
                INSERT INTO transactions (user_id, amount, kind, ref_type, ref_id, comment, created_at)
                VALUES (?, ?, ?, 'withdrawal', ?, ?, ?)
                """,
                (row["user_id"], -amount, TX_WITHDRAW_PAID, wid, f"{row['network']}", now_iso()),
            )
            return True, int(row["user_id"]), amount

    def reject_withdrawal(self, wid: int) -> tuple[bool, int | None, int]:
        """Отклонение: возвращает зарезервированную сумму в available."""
        with self.tx() as conn:
            row = conn.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)).fetchone()
            if row is None:
                return False, None, 0
            if row["status"] != WITHDRAW_PENDING:
                return False, int(row["user_id"]), int(row["amount"])
            cur = conn.execute(
                "UPDATE withdrawals SET status = ?, settled_at = ? WHERE id = ? AND status = ?",
                (WITHDRAW_REJECTED, now_iso(), wid, WITHDRAW_PENDING),
            )
            if cur.rowcount == 0:
                return False, int(row["user_id"]), int(row["amount"])
            amount = int(row["amount"])
            conn.execute(
                "UPDATE users SET available = available + ? WHERE id = ?",
                (amount, row["user_id"]),
            )
            # возврат резерва баланс не меняет — в журнал не пишем
            return True, int(row["user_id"]), amount

    # --- тикеты -----------------------------------------------------------

    def create_ticket(self, user_id: int, message: str) -> int:
        with self.tx() as conn:
            cur = conn.execute(
                "INSERT INTO tickets (user_id, message, status, created_at) VALUES (?, ?, 'open', ?)",
                (user_id, message, now_iso()),
            )
            return int(cur.lastrowid)

    def close_ticket(self, ticket_id: int) -> bool:
        with self.tx() as conn:
            cur = conn.execute(
                "UPDATE tickets SET status = 'answered', answered_at = ? WHERE id = ? AND status = 'open'",
                (now_iso(), ticket_id),
            )
            return cur.rowcount > 0

    def get_ticket(self, ticket_id: int) -> sqlite3.Row | None:
        with self.session() as conn:
            return conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()

    # --- операторы --------------------------------------------------------

    def seed_operators(self, operators: dict[str, dict]) -> None:
        with self.tx() as conn:
            for name, meta in operators.items():
                conn.execute(
                    "INSERT OR IGNORE INTO operator_state (operator, is_open) VALUES (?, ?)",
                    (name, 1 if meta.get("open", True) else 0),
                )

    def operators_state(self, defaults: dict[str, dict]) -> dict[str, bool]:
        with self.session() as conn:
            rows = conn.execute("SELECT operator, is_open FROM operator_state").fetchall()
        state = {row["operator"]: bool(row["is_open"]) for row in rows}
        for name, meta in defaults.items():
            state.setdefault(name, bool(meta.get("open", True)))
        return state

    def set_operator_open(self, operator: str, is_open: bool) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO operator_state (operator, is_open) VALUES (?, ?)
                ON CONFLICT(operator) DO UPDATE SET is_open = excluded.is_open
                """,
                (operator, 1 if is_open else 0),
            )

    def cleanup_old_orders(self, days: int) -> list[str]:
        """Обнуляет file_id и отдаёт пути локальных QR-файлов на удаление.

        Возвращает список файлов, которые вызывающий код удаляет с диска:
        срок хранения QR/eSIM ограничен (QR_RETENTION_DAYS).
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        with self.tx() as conn:
            paths = [
                row["qr_path"]
                for row in conn.execute(
                    "SELECT qr_path FROM orders WHERE qr_path IS NOT NULL AND created_at < ?",
                    (cutoff,),
                )
            ]
            conn.execute(
                "UPDATE orders SET file_id = NULL, qr_path = NULL "
                "WHERE (file_id IS NOT NULL OR qr_path IS NOT NULL) AND created_at < ?",
                (cutoff,),
            )
            return paths
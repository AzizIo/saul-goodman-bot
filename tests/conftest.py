import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from bot.db import Database  # noqa: E402


@pytest.fixture()
def database(tmp_path):
    db = Database(tmp_path / "test.db")
    db.init()
    db.seed_operators(config.OPERATORS)
    return db


@pytest.fixture()
def active_user(database):
    database.create_user(500, "seller")
    database.set_status(500, "active")
    return 500
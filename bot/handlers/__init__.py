"""Роутеры Saul Goodman ⚖️."""
from __future__ import annotations

from aiogram import Router

from bot.handlers import admin, common, orders, profile, support, withdraw


def build_router(database) -> Router:
    root = Router(name="root")
    root.include_router(common.build_router(database))
    root.include_router(admin.build_router(database))
    root.include_router(orders.build_router(database))
    root.include_router(profile.build_router(database))
    root.include_router(withdraw.build_router(database))
    root.include_router(support.build_router(database))
    return root


__all__ = ["build_router", "common", "admin", "orders", "profile", "support", "withdraw"]
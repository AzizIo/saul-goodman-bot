"""Валидация ввода Saul Goodman ⚖️."""
from __future__ import annotations

import re

PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-()]{7,19}$")

WALLET_NETWORKS = {
    "bep20": ("USDT BEP20", re.compile(r"^0x[a-fA-F0-9]{40}$")),
    "trc20": ("USDT TRC20", re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")),
}


def normalize_phone(text: str) -> str | None:
    """Возвращает номер в виде +7XXXXXXXXXX или None, если формат не тот."""
    if not text:
        return None
    cleaned = text.strip()
    # берём первый «похожий на телефон» токен из подписи
    tokens = re.split(r"[\s,;|/]+", cleaned)
    candidate = cleaned if PHONE_RE.match(cleaned) else None
    if candidate is None:
        for token in tokens:
            if PHONE_RE.match(token):
                candidate = token
                break
    if candidate is None:
        return None
    digits = re.sub(r"[^0-9]", "", candidate)
    if not 10 <= len(digits) <= 15:
        return None
    return ("+" if candidate.startswith("+") else "") + digits


def parse_wallet(text: str) -> tuple[str, str] | None:
    """'USDT BEP20 0x...' -> ('USDT BEP20', '0x...'); голый адрес -> TRC20."""
    if not text:
        return None
    raw = text.strip()
    upper = raw.upper()

    network = None
    if "BEP20" in upper or upper.startswith("BSC"):
        network = "bep20"
    elif "TRC20" in upper or upper.startswith("TRON"):
        network = "trc20"

    address = raw
    for marker in ("BEP20", "TRC20", "BSC", "TRON", "USDT"):
        address = re.sub(marker, " ", address, flags=re.IGNORECASE)
    address = address.strip().strip(",;|").strip()
    tokens = [t for t in re.split(r"\s+", address) if t]
    address = tokens[0] if tokens else ""
    address = address.strip(",;|")

    if not address:
        return None

    if network is None:
        network = "bep20" if address.startswith("0x") else "trc20"

    label, pattern = WALLET_NETWORKS[network]
    if not pattern.match(address):
        return None
    return label, address
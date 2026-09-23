"""Synthetic demo data. Regenerate with: python data/generate.py

Real client data never goes into this repo. Replace the generator on the day
if the case gives its own dataset.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.config import DATA_DIR


@lru_cache(maxsize=None)
def _load(name: str) -> Any:
    path = DATA_DIR / name
    if not path.exists():
        return [] if name != "demo_prompts.json" else []
    return json.loads(path.read_text(encoding="utf-8"))


def clients() -> list[dict]:
    return _load("clients.json")


def transactions() -> list[dict]:
    return _load("transactions.json")


def applications() -> list[dict]:
    return _load("applications.json")


def flagged_recipients() -> set[str]:
    return set(_load("antifraud_list.json"))


def demo_prompts() -> list[dict]:
    return _load("demo_prompts.json")


def get_client(client_id: str) -> dict | None:
    return next((c for c in clients() if c["client_id"] == client_id), None)


def transactions_for(client_id: str) -> list[dict]:
    rows = [t for t in transactions() if t["client_id"] == client_id]
    return sorted(rows, key=lambda t: t["ts"], reverse=True)


def get_transaction(tx_id: str) -> dict | None:
    return next((t for t in transactions() if t["tx_id"] == tx_id), None)


def applications_for(client_id: str) -> list[dict]:
    rows = [a for a in applications() if a["client_id"] == client_id]
    return sorted(rows, key=lambda a: a["ts"])


def reset_cache() -> None:
    _load.cache_clear()

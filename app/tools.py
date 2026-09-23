"""Tools the model can call. Money math and data access live here, in code.

Rule: the model never does arithmetic itself. It calls a tool and explains the
result. Every tool has a strict JSON schema so the model cannot invent fields.

To add a tool: write a function, decorate it with @tool(...), add a test in
tests/test_tools.py. The agent sees it automatically.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable

from app import data

TOOLS: dict[str, dict[str, Any]] = {}


def tool(name: str, description: str, properties: dict[str, dict]) -> Callable:
    """Register a function as a strict OpenAI function tool."""

    def wrap(fn: Callable) -> Callable:
        TOOLS[name] = {
            "fn": fn,
            "schema": {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }
        return fn

    return wrap


def _money(x: Decimal | float) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ---------- money math ----------


@tool(
    "loan_payment",
    "Аннуитетный ежемесячный платёж по кредиту, общая сумма выплат и переплата. "
    "Используй для любых расчётов платежей по кредиту.",
    {
        "principal_kzt": {"type": "number", "description": "Сумма кредита в тенге"},
        "annual_rate_pct": {"type": "number", "description": "Годовая ставка в процентах, например 24.5"},
        "months": {"type": "integer", "description": "Срок в месяцах"},
    },
)
def loan_payment(principal_kzt: float, annual_rate_pct: float, months: int) -> dict:
    if principal_kzt <= 0 or months <= 0 or annual_rate_pct < 0:
        return {"error": "principal_kzt и months должны быть больше 0, ставка не отрицательная"}
    p = Decimal(str(principal_kzt))
    n = int(months)
    r = Decimal(str(annual_rate_pct)) / Decimal(100) / Decimal(12)
    if r == 0:
        payment = p / n
    else:
        payment = p * r / (1 - (1 + r) ** (-n))
    total = payment * n
    return {
        "monthly_payment_kzt": _money(payment),
        "total_paid_kzt": _money(total),
        "overpayment_kzt": _money(total - p),
        "months": n,
        "annual_rate_pct": float(annual_rate_pct),
    }


@tool(
    "debt_burden",
    "Коэффициент долговой нагрузки (КДН): доля ежемесячных платежей по долгам в доходе. "
    "Лимит в Казахстане 50% (проверить актуальность в кейсе).",
    {
        "monthly_income_kzt": {"type": "number", "description": "Подтверждённый ежемесячный доход"},
        "monthly_debt_payments_kzt": {
            "type": "number",
            "description": "Все ежемесячные платежи по долгам, включая новый кредит",
        },
    },
)
def debt_burden(monthly_income_kzt: float, monthly_debt_payments_kzt: float) -> dict:
    if monthly_income_kzt <= 0:
        return {"error": "доход должен быть больше 0"}
    ratio = Decimal(str(monthly_debt_payments_kzt)) / Decimal(str(monthly_income_kzt)) * 100
    ratio_pct = _money(ratio)
    return {
        "debt_burden_pct": ratio_pct,
        "limit_pct": 50.0,
        "within_limit": ratio_pct <= 50.0,
    }


# ---------- data access ----------


@tool(
    "client_profile",
    "Профиль клиента из демо-данных: город, возраст, доход, сегмент, продукты.",
    {"client_id": {"type": "string", "description": "ID клиента, например C-DEMO-1"}},
)
def client_profile(client_id: str) -> dict:
    client = data.get_client(client_id)
    return client if client else {"error": f"клиент {client_id} не найден"}


@tool(
    "recent_transactions",
    "Последние операции клиента (новые сверху).",
    {
        "client_id": {"type": "string"},
        "limit": {"type": "integer", "description": "Сколько операций вернуть, 1-50"},
    },
)
def recent_transactions(client_id: str, limit: int) -> dict:
    limit = max(1, min(int(limit), 50))
    rows = data.transactions_for(client_id)
    if not rows:
        return {"error": f"операций клиента {client_id} нет"}
    public = [{k: v for k, v in r.items() if k != "is_fraud"} for r in rows[:limit]]
    return {"client_id": client_id, "count": len(rows), "transactions": public}


@tool(
    "fraud_signals",
    "Правила антифрода для одной операции: ночное время, новый получатель, новое устройство, "
    "сумма сильно выше обычной, получатель в стоп-листе, серия заявок на займы за час. "
    "Возвращает сработавшие сигналы и балл правил 0-100.",
    {"transaction_id": {"type": "string", "description": "ID операции, например T-DEMO-1"}},
)
def fraud_signals(transaction_id: str) -> dict:
    tx = data.get_transaction(transaction_id)
    if not tx:
        return {"error": f"операция {transaction_id} не найдена"}
    history = [
        t["amount_kzt"]
        for t in data.transactions_for(tx["client_id"])
        if t["tx_id"] != tx["tx_id"] and t["type"] in ("card_payment", "qr_payment", "p2p_transfer")
    ]
    median = statistics.median(history) if history else 0
    ts = datetime.fromisoformat(tx["ts"])
    signals: list[dict] = []

    def add(code: str, text: str, weight: int) -> None:
        signals.append({"code": code, "text": text, "weight": weight})

    if 0 <= ts.hour < 6:
        add("night", f"операция ночью ({ts:%H:%M})", 15)
    if tx.get("recipient_is_new"):
        add("new_recipient", "перевод новому получателю", 20)
    if tx.get("device_is_new"):
        add("new_device", "вход с нового устройства", 20)
    if median and tx["amount_kzt"] >= 3 * median:
        add("amount_spike", f"сумма в {tx['amount_kzt'] / median:.1f} раза выше медианы клиента", 20)
    if tx.get("recipient_id") in data.flagged_recipients():
        add("flagged_recipient", "получатель в стоп-листе антифрода", 35)

    apps = data.applications_for(tx["client_id"])
    tx_time = ts
    recent_apps = [
        a for a in apps if 0 <= (tx_time - datetime.fromisoformat(a["ts"])).total_seconds() <= 24 * 3600
    ]
    for i in range(len(recent_apps)):
        window = [
            a
            for a in recent_apps
            if 0
            <= (datetime.fromisoformat(a["ts"]) - datetime.fromisoformat(recent_apps[i]["ts"])).total_seconds()
            <= 3600
        ]
        if len(window) >= 3:
            add("loan_burst", f"{len(window)} заявки на займы в течение часа за сутки до операции", 25)
            break

    score = min(100, sum(s["weight"] for s in signals))
    return {
        "transaction_id": transaction_id,
        "amount_kzt": tx["amount_kzt"],
        "client_median_kzt": _money(median) if median else None,
        "signals": signals,
        "rule_score": score,
    }


# ---------- plumbing ----------


def openai_tools(names: list[str] | None = None) -> list[dict]:
    selected = TOOLS if names is None else {n: TOOLS[n] for n in names if n in TOOLS}
    return [t["schema"] for t in selected.values()]


def call_tool(name: str, arguments: str | dict) -> dict:
    """Run a tool by name. Never raises: errors come back as {'error': ...}."""
    entry = TOOLS.get(name)
    if entry is None:
        return {"error": f"неизвестный инструмент {name}"}
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        return entry["fn"](**args)
    except Exception as exc:  # the model sees the error and can recover
        return {"error": f"{type(exc).__name__}: {exc}"}

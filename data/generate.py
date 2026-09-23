"""Generate synthetic demo data (deterministic). Run: python data/generate.py

Creates clients, transactions, loan applications, an antifraud stop-list and
three showcase records used by the demo prompts:
  T-DEMO-1  night transfer to a stop-listed new recipient from a new device,
            right after 3 microloan applications within an hour (classic scam)
  T-DEMO-2  normal daytime QR payment
  C-DEMO-2  loan applicant whose debt burden goes above 50% with the new loan
No real people: names are generic, IDs are synthetic.
"""
from __future__ import annotations

import sys

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # UTF-8 output on Windows too (Codex reads it)
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OUT = Path(__file__).resolve().parent
REF = datetime(2026, 9, 22, 12, 0)  # fixed "now" so data never changes between runs
rng = random.Random(23092026)

CITIES = ["Астана", "Алматы", "Шымкент", "Караганда", "Актобе", "Павлодар", "Усть-Каменогорск", "Атырау"]
FIRST = ["Айгерим", "Данияр", "Алия", "Нурлан", "Жанна", "Ерлан", "Динара", "Арман", "Сауле", "Тимур",
         "Мадина", "Руслан", "Асель", "Бекзат", "Камила", "Олжас", "Анна", "Дмитрий", "Ольга", "Сергей"]
LAST_INITIALS = "АБГДЕЖЗИКЛМНОПРСТУШ"
SEGMENTS = ["mass", "mass", "mass", "premium", "sme"]
LENDERS = ["Банк A", "Банк B", "Банк C", "МФО D", "МФО E"]
MERCHANTS = ["продукты", "кафе", "АЗС", "аптека", "такси", "маркетплейс", "одежда", "связь", "коммунальные"]


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def make_clients() -> list[dict]:
    clients = []
    for i in range(1, 41):
        income = rng.choice([180, 250, 320, 400, 520, 650, 800, 1200]) * 1000
        clients.append({
            "client_id": f"C{i:03d}",
            "name": f"{rng.choice(FIRST)} {rng.choice(LAST_INITIALS)}.",
            "city": rng.choice(CITIES),
            "age": rng.randint(19, 67),
            "segment": rng.choice(SEGMENTS),
            "monthly_income_kzt": income,
            "monthly_debt_payments_kzt": int(income * rng.choice([0, 0, 0.1, 0.2, 0.3, 0.4])),
            "products": rng.sample(["карта", "депозит", "кредит", "рассрочка", "ИП-счёт"], k=rng.randint(1, 3)),
            "client_since": rng.randint(2014, 2026),
        })
    clients += [
        {"client_id": "C-DEMO-1", "name": "Сауле Т.", "city": "Астана", "age": 58, "segment": "mass",
         "monthly_income_kzt": 280000, "monthly_debt_payments_kzt": 0, "products": ["карта", "депозит"],
         "client_since": 2016},
        {"client_id": "C-DEMO-2", "name": "Арман К.", "city": "Алматы", "age": 34, "segment": "mass",
         "monthly_income_kzt": 600000, "monthly_debt_payments_kzt": 250000, "products": ["карта", "кредит"],
         "client_since": 2019},
        {"client_id": "C-DEMO-3", "name": "Мадина Е.", "city": "Астана", "age": 27, "segment": "premium",
         "monthly_income_kzt": 900000, "monthly_debt_payments_kzt": 90000, "products": ["карта", "рассрочка"],
         "client_since": 2021},
    ]
    return clients


def make_transactions(clients: list[dict]) -> list[dict]:
    rows: list[dict] = []
    n = 0
    for c in clients:
        known_recipients = [f"R-{rng.randint(1000, 6999)}" for _ in range(6)]
        for _ in range(rng.randint(20, 40)):
            n += 1
            kind = rng.choices(["card_payment", "qr_payment", "p2p_transfer", "cash_withdrawal"], [40, 35, 20, 5])[0]
            base = {"card_payment": 9000, "qr_payment": 6000, "p2p_transfer": 25000, "cash_withdrawal": 40000}[kind]
            amount = int(base * rng.lognormvariate(0, 0.7)) // 100 * 100 + 100
            ts = (REF - timedelta(days=rng.randint(0, 29))).replace(hour=rng.randint(8, 22), minute=rng.randint(0, 59))
            if ts > REF:
                ts -= timedelta(days=1)
            new_recipient = kind == "p2p_transfer" and rng.random() < 0.15
            rows.append({
                "tx_id": f"T{n:05d}",
                "client_id": c["client_id"],
                "ts": iso(ts),
                "type": kind,
                "amount_kzt": amount,
                "channel": {"cash_withdrawal": "atm", "card_payment": "pos"}.get(kind, "app"),
                "merchant": rng.choice(MERCHANTS) if kind in ("card_payment", "qr_payment") else None,
                "recipient_id": (f"R-{rng.randint(7000, 9999)}" if new_recipient else rng.choice(known_recipients))
                if kind == "p2p_transfer" else None,
                "recipient_is_new": new_recipient,
                "device_is_new": rng.random() < 0.03,
                "city": c["city"],
                "is_fraud": False,
            })
    # a few random frauds with the usual pattern
    for t in rng.sample([r for r in rows if r["type"] == "p2p_transfer"], k=8):
        t.update(is_fraud=True, recipient_is_new=True, device_is_new=True, amount_kzt=t["amount_kzt"] * 6,
                 ts=iso(datetime.fromisoformat(t["ts"]).replace(hour=rng.randint(0, 4))),
                 recipient_id=f"R-{rng.randint(9000, 9999)}")
    # showcase records
    rows.append({"tx_id": "T-DEMO-1", "client_id": "C-DEMO-1", "ts": "2026-09-22T03:12:00", "type": "p2p_transfer",
                 "amount_kzt": 450000, "channel": "app", "merchant": None, "recipient_id": "R-9781",
                 "recipient_is_new": True, "device_is_new": True, "city": "Астана", "is_fraud": True})
    rows.append({"tx_id": "T-DEMO-2", "client_id": "C-DEMO-3", "ts": "2026-09-21T13:40:00", "type": "qr_payment",
                 "amount_kzt": 8500, "channel": "app", "merchant": "продукты", "recipient_id": None,
                 "recipient_is_new": False, "device_is_new": False, "city": "Астана", "is_fraud": False})
    return sorted(rows, key=lambda r: r["ts"])


def make_applications(clients: list[dict]) -> list[dict]:
    apps: list[dict] = []
    for i in range(1, 61):
        c = rng.choice(clients[:40])
        product = rng.choice(["microloan", "consumer_loan", "credit_card"])
        apps.append({
            "app_id": f"A{i:04d}",
            "client_id": c["client_id"],
            "ts": iso(REF - timedelta(days=rng.randint(0, 60), hours=rng.randint(0, 23))),
            "product": product,
            "amount_kzt": {"microloan": 150000, "consumer_loan": 1200000, "credit_card": 500000}[product]
            * rng.choice([1, 1, 2]),
            "term_months": {"microloan": 3, "consumer_loan": 24, "credit_card": 12}[product],
            "lender": rng.choice(LENDERS),
            "status": rng.choice(["approved", "declined", "pending"]),
        })
    for j, t in enumerate(["2026-09-21T23:05:00", "2026-09-21T23:20:00", "2026-09-21T23:48:00"], start=1):
        apps.append({"app_id": f"A-DEMO-1{j}", "client_id": "C-DEMO-1", "ts": t, "product": "microloan",
                     "amount_kzt": 150000, "term_months": 3, "lender": LENDERS[2 + j % 3], "status": "approved"})
    apps.append({"app_id": "A-DEMO-2", "client_id": "C-DEMO-2", "ts": "2026-09-22T10:30:00",
                 "product": "consumer_loan", "amount_kzt": 1500000, "term_months": 24, "lender": "Банк A",
                 "status": "pending", "annual_rate_pct": 24.0})
    return sorted(apps, key=lambda a: a["ts"])


def main() -> None:
    clients = make_clients()
    transactions = make_transactions(clients)
    applications = make_applications(clients)
    flagged = sorted({t["recipient_id"] for t in transactions if t["is_fraud"] and t["recipient_id"]})
    files = {
        "clients.json": clients,
        "transactions.json": transactions,
        "applications.json": applications,
        "antifraud_list.json": flagged,
    }
    for name, rows in files.items():
        (OUT / name).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"clients {len(clients)}, transactions {len(transactions)}, applications {len(applications)}, "
          f"stop-list {len(flagged)}")


if __name__ == "__main__":
    main()

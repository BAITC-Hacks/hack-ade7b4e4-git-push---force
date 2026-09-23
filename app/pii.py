"""Mask personal data before any text is sent to a model.

Kazakhstan-specific: IIN/BIN (12 digits), KZ IBAN, +7 phones, card numbers
(Luhn-checked, last 4 kept), emails. Amounts like 450 000 are left alone.
"""
from __future__ import annotations

import re

IBAN_KZ = re.compile(r"\bKZ\d{2}[A-Z0-9]{16}\b", re.IGNORECASE)
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE = re.compile(r"(?<!\d)(?:\+7|8)[\s\-(]*7\d{2}[\s\-)]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)")
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
IIN = re.compile(r"(?<!\d)\d{12}(?!\d)")


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Return (masked_text, kinds_found)."""
    found: list[str] = []

    def sub(pattern: re.Pattern, label: str, s: str) -> str:
        def repl(m: re.Match) -> str:
            found.append(label)
            return f"[{label}]"

        return pattern.sub(repl, s)

    out = sub(IBAN_KZ, "IBAN", text)
    out = sub(EMAIL, "EMAIL", out)
    out = sub(PHONE, "ТЕЛЕФОН", out)

    def card_repl(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            found.append("КАРТА")
            return f"[КАРТА *{digits[-4:]}]"
        return m.group(0)

    out = CARD.sub(card_repl, out)
    out = sub(IIN, "ИИН", out)
    return out, found

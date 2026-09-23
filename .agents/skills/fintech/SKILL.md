---
name: fintech
description: Kazakhstan fintech domain reference for the HackAlem fintech track. Patterns for antifraud, credit scoring, AML/KYC, bank support agents, payments analytics, with data, tools, guardrails, metrics and verified local rules. Use when mapping the case, designing tools or schemas, or when the user asks about fintech, banks, fraud, loans, КДН or regulation.
---

# fintech

Full reference: `docs/FINTECH_PLAYBOOK.md`. Read the section for the matched pattern only.

## Map the case to a pattern
| If the case is about | Pattern | Core tools | Key output fields |
| suspicious transfers, scams, drops | Antifraud copilot | fraud_signals, recent_transactions | decision, risk_level, reasons, needs_human |
| loans, limits, affordability | Credit decision assistant | loan_payment, debt_burden, client_profile | decision, payment, КДН, reasons |
| documents, sanctions, onboarding | AML/KYC checker | document fields extraction, list lookup | status, missing items, reasons |
| customer messages, complaints | Support triage agent | classify intent, FAQ/RAG lookup | category, answer, escalate |
| payments, QR, merchants, SME cash flow | Payments analytics agent | aggregate, compare periods | insight, numbers from code |

## Non-negotiables for any fintech demo
1. Money math in code (`app/tools.py`), never in the model text.
2. Every decision has reasons tied to data; risky actions need a human (`needs_human`).
3. Personal data is masked before the model; data is synthetic.
4. Prompt injection is refused on camera.
5. One scenario in Kazakh.
6. Show cost per request and the share handled by the cheap model.

## Local facts you may use (with source and date in docs/FINTECH_PLAYBOOK.md)
- Debt burden ratio limit (КДН) 50%; self-ban on loans via eGov; cooling-off 8h or 24h for large loans.
- National Bank Antifraud Center: 80 871 fraud incidents registered as of 01.01.2026, 2.8 bn tenge blocked.
- Unified QR: 20 mn transactions for 400+ bn tenge in its first 2 months, 25% of the payments market.
Always tell the team to re-check a rule against the case text: the case wins over this file.

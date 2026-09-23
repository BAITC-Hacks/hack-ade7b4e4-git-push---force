"""Run the agent on evals/cases.jsonl and measure quality, cost and speed.

    python scripts/run_eval.py

Each line of cases.jsonl:
  {"id": "...", "message": "...", "client_id": "C-DEMO-1" or null,
   "expect": {"decision": ["review", "decline"], "risk_level": ["high"], "needs_human": true}}
A case passes when every expected field matches (a list means "any of").
Writes evals/results.json. These numbers go on the metrics slide.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import agent, llm  # noqa: E402

for _stream in (sys.stdout, sys.stderr):  # UTF-8 output on Windows too (Codex reads it)
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CASES = ROOT / "evals" / "cases.jsonl"
RESULTS = ROOT / "evals" / "results.json"


def matches(expected, actual) -> bool:
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def main() -> int:
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    if llm.mode() != "live":
        print("ВНИМАНИЕ: демо-режим (нет ключа или DEMO_MODE=on). Цифры не отражают модель.")
    rows = []
    for case in cases:
        answer, meta = agent.ask(case["message"], case.get("client_id"))
        got = answer.model_dump()
        misses = {k: got.get(k) for k, v in case.get("expect", {}).items() if not matches(v, got.get(k))}
        rows.append({
            "id": case["id"], "pass": not misses, "misses": misses,
            "decision": got.get("decision"), "risk_level": got.get("risk_level"),
            "tier": meta["tier"], "escalated": meta["escalated"], "model": meta.get("model"),
            "cost_usd": meta.get("cost_usd"), "latency_ms": meta["latency_ms"],
            "tools": [t["name"] for t in meta.get("tools_called", [])], "mode": meta["mode"],
        })
        mark = "OK  " if not misses else "MISS"
        print(f"{mark} {case['id']:<18} {str(got.get('decision')):<8} {meta['tier']:<5} "
              f"{meta['latency_ms']:>6} мс  ${meta.get('cost_usd') or 0:.5f}  {misses if misses else ''}")

    n = len(rows) or 1
    passed = sum(r["pass"] for r in rows)
    fast = sum(1 for r in rows if r["tier"] == "fast" and not r["escalated"])
    total_cost = sum(r["cost_usd"] or 0 for r in rows)
    summary = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "mode": llm.mode(),
        "cases": len(rows),
        "passed": passed,
        "accuracy_pct": round(100 * passed / n, 1),
        "share_fast_pct": round(100 * fast / n, 1),
        "total_cost_usd": round(total_cost, 5),
        "avg_cost_usd": round(total_cost / n, 6),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / n),
        "rows": rows,
    }
    RESULTS.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nИтог: {passed}/{len(rows)} верно ({summary['accuracy_pct']}%), на быстрой модели "
          f"{summary['share_fast_pct']}%, всего ${summary['total_cost_usd']}, в среднем {summary['avg_latency_ms']} мс")
    print(f"Сохранено: {RESULTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

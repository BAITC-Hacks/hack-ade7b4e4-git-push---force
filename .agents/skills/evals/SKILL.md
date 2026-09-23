---
name: evals
description: Build a 15-20 case evaluation set for the solved case and measure accuracy, cost, share of cheap-model answers and latency with scripts/run_eval.py. Use when the user runs $evals, asks "проверь качество", "сколько стоит запрос", or needs numbers for the pitch.
---

# evals

Numbers on the metrics slide must be measured, never estimated. This skill produces them.

## Step 1: write the cases (evals/cases.jsonl, one JSON per line)
15-20 cases taken from `specs/solution.md`:
- 6-8 golden path variations (the demo scenario with different inputs)
- 3-4 edge cases from the spec (missing data, unknown ID, borderline amounts)
- 2 prompt injection attempts
- 2 Kazakh-language requests
- 2 clearly normal cases (the agent must not panic)
Use only IDs that exist in the synthetic data. Check with a one-liner, for example:
`python -c "from app import data; print([t['tx_id'] for t in data.transactions() if t['is_fraud']][:10])"`
Expected values are lists of acceptable answers:
`{"id": "fraud-1", "message": "...", "client_id": "C-DEMO-1", "expect": {"decision": ["review", "decline"], "risk_level": ["high"]}}`
If the agent schema changed, expect the new field names.

## Step 2: estimate cost, then run
Tell the user: cases x about 2 model calls each. With the fast model this is cents.
Run `python scripts/run_eval.py` only after the user agrees (it spends the team's API budget).

## Step 3: read the result (evals/results.json)
Report in Russian, 5 lines: accuracy, share on the fast model, total and per-request cost,
average latency, the failing case IDs.
If accuracy is below 80%, group failures by cause (prompt, missing tool, schema, data) and propose
the smallest fix as a `$build` unit. Never change an expected value just to pass.

## Step 4: commit
`git add evals && git commit -m "evals: <N> cases, <accuracy>% (U<n>)"`

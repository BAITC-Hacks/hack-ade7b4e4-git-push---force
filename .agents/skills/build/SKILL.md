---
name: build
description: Implement exactly one work unit from specs/solution.md, prove it with a check, commit it. Use when the user runs $build, says "делай U2", "следующий юнит" or "реализуй". Builds the spec, not ideas beyond it.
---

# build (hackathon mode)

Take one unit (U1, U2, ...) from `specs/solution.md` and turn it into working, committed code.
The discipline that makes this useful is restraint: build what the unit says, no more, no less.

## The one rule that matters most: build the spec, not your idea of it
- No features that are not in the spec. Not even small nice ones. Note them instead.
- No refactoring of unrelated code.
- No invented requirements. If the spec is silent on something you need, ask one question.
If you are about to write code and cannot point to the requirement it satisfies, do not write it.

## Step 1: pick the unit
The one the user named, otherwise the first unchecked `- [ ] U<n>`. If `specs/solution.md` is
missing, say so and suggest `$spec`. Do not build from memory of the chat.

## Step 2: read only what the unit needs
The unit lists ЦЕЛЬ, ГДЕ, НЕЛЬЗЯ, ГОТОВО. Open the files in ГДЕ plus AGENTS.md rules.
Typical places:
- Agent behaviour: `app/agent.py` (CASE_CONTEXT, AgentAnswer fields, TOOLS). Keep SYSTEM_PROMPT static.
- A calculation or data lookup: a new `@tool` in `app/tools.py` plus a test in `tests/test_tools.py`.
- A safety rule (for example "high risk needs a human"): `app/guardrails.py` plus `tests/test_guardrails.py`.
  If you change AgentAnswer fields, update the guardrails in the same unit.
- Case data: `data/generate.py`, then `python data/generate.py`. Keep showcase IDs stable.
- A new endpoint: `app/main.py`, declared above the static mount.
- The screen: `static/app.js` (`show()` renders the answer), `static/index.html`, `static/style.css`.
- Demo buttons: `data/demo_prompts.json`.

## Step 3: test first for the ГОТОВО check
Write or update the test the unit names. Tests are fast and never call the network
(demo mode, or the fake client pattern from `tests/test_llm_offline.py`).

## Step 4: implement the smallest change
Then run `python scripts/check.py` until it prints OK. If the unit touches the demo path,
also run `python scripts/smoke.py`. Never start the server as a check.

## Step 5: record and commit
- Tick the unit in `specs/solution.md` (`- [x] U<n>`).
- 3 lines in `docs/progress.md`: done, now, next.
- `git add -A` then `git commit -m "<area>: <what> (U<n>)"`, then `git push`.

## Step 6: report (short, in Russian)
Unit, files changed, check result, decisions you had to make, things noticed but not done.
Then stop. The user decides what is next (usually `$review` after 2-3 units).

## Timebox
If a unit is not green after about 40 minutes, stop and propose a smaller version of it.
Five hours total. A working narrow path beats an unfinished wide one.

# AGENTS.md

HackAlem AI hackathon, fintech track. Coding window: 23.09.2026, 13:00-18:00 (5 hours).
Judges read the repo history and open the live link during 24-28.09.
Talk to the team in Russian. Short sentences. No em dashes.

## Map
- `app/main.py`: FastAPI routes; the static UI is mounted last.
- `app/agent.py`: the domain agent (CASE_CONTEXT, SYSTEM_PROMPT, AgentAnswer schema, TOOLS). Adapted to the case.
- `app/llm.py`: the ONLY module that calls OpenAI. Routing, tool loop, Structured Outputs, cache, cost, fallback.
- `app/tools.py`: money math and data access as strict function tools. `app/router.py`: fast or smart tier.
- `app/pii.py`: masks IIN, cards, phones, IBAN, email. `app/config.py`: all settings from env.
- `app/guardrails.py`: safety rules enforced in code after every answer (high risk never auto-approved, etc.).
- `app/data.py`, `data/`: synthetic data. Regenerate: `python data/generate.py`.
  Never open `data/*.json` whole (big). Inspect with a short python one-liner.
- `static/`: UI (index.html, app.js, style.css). No build step.
- `docs/CASE.md`: the case text. `specs/solution.md`: the spec, source of truth.
- `reviews/`: review reports. `docs/progress.md`: where we are. `evals/cases.jsonl`: quality set.

## Commands
Which Python to use, in this order (check once per session, then stick to it):
1. The project virtualenv (`.venv/bin/python`, Windows `.venv\Scripts\python.exe`) if it exists and
   `<it> -c "import fastapi, pytest"` succeeds.
2. Otherwise the system `python` (Windows also `py`) if `python -c "import fastapi, pytest"` succeeds.
   On Windows with Cyrillic in the user path the venv launcher breaks: the system Python is expected there.
3. Otherwise stop and ask the user to run `python -m pip install -r requirements-dev.txt`.
Never create a virtualenv yourself. Every `python ...` below means the interpreter chosen above.
- Check after every change: `python scripts/check.py` (one-line summary, full log in logs/check.log)
- Smoke: `python scripts/smoke.py`. Deployed: `python scripts/smoke.py --url <URL>`
- Quality, cost, speed: `python scripts/run_eval.py` (spends API budget, ask first)
- Key and model names: `python scripts/check_key.py`. Save demo answers: `python scripts/warm_cache.py`
- Humans run the server: `python -m uvicorn app.main:app --reload`
- NEVER run the server, `vercel dev` or any watcher as a check. They never exit and hang you.

## Skills (.agents/skills)
Order: `spec` -> `build` (one unit at a time) -> `review` -> `checkpoint` every hour.
Also: `evals`, `deploy`, `pitch`, `fintech` (domain reference).
If the user writes a skill name without `$`, or `$` does not autocomplete,
open `.agents/skills/<name>/SKILL.md` and follow it.
Custom agents in `.codex/agents`: `reviewer`, `qa`, `judge`. Spawn them only when a skill or the user asks.

## Rules
1. Think before coding. State assumptions in one line. If blocked, ask one question.
2. Simplicity first. The smallest change that satisfies the spec.
3. Surgical changes. Touch only what the task needs. No drive-by refactors.
4. Goal-driven. Every task ends with a named check passing.
5. Money math lives only in `app/tools.py`, each function with a test. The model never computes numbers.
6. Every model call goes through `app/llm.py`. Default provider: OpenAI API (team credits).
   NVIDIA Build is allowed only if the spec asks for it. API keys never go into git (organizers' rule).
7. Synthetic data only. Mask with `app/pii.py` before any model call. Never log raw personal data.
8. No new dependencies without asking. No secrets in code; keys live in `.env` and `app/config.py`.
9. Keep SYSTEM_PROMPT static (no dates, no user data): a stable prefix gets prompt caching.
10. Wrong code is deleted, not commented out. No stubs left on the demo path.
11. Never edit a test just to make it pass. Tests change only when the spec changes.
12. UI text in Russian. Keep at least one demo scenario in Kazakh.
13. Tests never hit the network. Use demo mode or the fake client pattern in `tests/test_llm_offline.py`.
14. Safety rules live in code (`app/guardrails.py`), not only in the prompt. When the answer schema
    changes, update the guardrails and `tests/test_guardrails.py` in the same unit.

## Git
- Commit after every green check, and at least once per hour (rule 6.6). Use `$checkpoint`.
- Message format: `<area>: <what> (U<n>)`, for example `agent: add fraud_signals tool (U2)`.
- Never `git stash`, never force-push, never rewrite history. Judges read it (rule 6.5).
- After 18:00 no commits unless the team lead confirms the rules allow it.

## Hackathon rules that touch the code
- Pre-made code is disclosed in README, section "Раскрытие" (rule 6.4). Keep it, update the "during the hackathon" list.
- The live link must work 24-28.09 (rules 8.7-8.9). Keep the demo cache and fallback working.
- The team solves ONE case of the track. All mandatory requirements of that case come first.
- README follows the organizers' structure (see the pitch skill). Submission: «Сдать решение» on the platform.

## Context hygiene
After each unit write 3 lines to `docs/progress.md`: done, now, next.
When the user says "новая сессия", update progress.md first, then stop.

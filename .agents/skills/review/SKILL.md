---
name: review
description: Audit the current work against specs/solution.md with evidence, run independent reviewer and qa agents on the diff, and gate it with PASS or CHANGES REQUESTED plus a fix list. Use when the user runs $review, asks "проверь", "всё ли готово", or after every 2-3 units. Audits only, does not fix.
---

# review (hackathon mode)

Check whether the work actually satisfies the spec, and gate it. Trust the code, not claims about it.

## The one rule that matters most: verify independently, gate strictly
1. Verify against the code and by running it, not against build reports or commit messages.
2. When you cannot show evidence that an item is met, it is not met.

## Step 1: collect the diff
`git log --oneline -15` and `git diff <last reviewed commit>..HEAD` (if unknown, the last 5 commits).

## Step 2: spawn two independent agents, in parallel
- `reviewer`: give it ONLY the diff. It assumes the code is wrong and hunts for real failures.
- `qa`: runs `python scripts/check.py` and `python scripts/smoke.py` and reports.
Say explicitly: "Spawn the reviewer agent with only this diff, and the qa agent. Wait for both."
If subagents are unavailable, do both jobs yourself, reviewer role first, with a fresh skeptical eye.

## Step 3: audit the spec item by item
For each R, E and A item in `specs/solution.md`: read the code that should satisfy it and run it
where possible. Hackathon-specific checks that are always blocking:
- the demo path from the spec works end to end (smoke passes, demo prompts answer)
- money math comes from `app/tools.py`, not from model text
- no raw personal data reaches the model or the logs; no secrets in the repo
- prompt injection demo prompt is refused
- the app still answers in demo mode (no key) for every demo prompt
Everything cosmetic is a note, not a blocker.

## Step 4: write reviews/review-<HHMM>.md (in Russian)
```markdown
# Ревью <HH:MM>
Вердикт: PASS | CHANGES REQUESTED (N из M пунктов не выполнены)

## Требования и приёмка
- [x] R1 ... Выполнено: <файл:функция или команда, что показала>
- [ ] A2 ... НЕ выполнено: <что не так>

## Находки reviewer
- BLOCKER app/tools.py:42 ... (как воспроизвести) -> что поменять

## Исправления для $build
1. (A2) <проблема> в <файл:функция>. Нужно: <конкретное изменение>.

## Заметки (не блокируют)
```

## Step 5: stop
Do not fix anything yourself: a reviewer who patches loses independence. Hand the fix list to
`$build`, then review again. Loop until PASS or until the time plan says freeze.

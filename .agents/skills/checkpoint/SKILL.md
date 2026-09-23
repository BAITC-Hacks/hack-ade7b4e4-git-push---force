---
name: checkpoint
description: Hourly save point required by the hackathon rules (commit at least once per hour). Runs the check, updates docs/progress.md, commits and pushes. Use when the user runs $checkpoint, says "коммит", "чекпоинт", or at :50 of every hour.
---

# checkpoint

Rule 6.6 of the hackathon: progress is recorded by a commit at least once per hour.
Judges read the history (rule 6.5), so every checkpoint must be honest and readable.

## Steps
1. `python scripts/check.py`. Note the result, do not try to fix anything now.
2. Update `docs/progress.md`: add a block with the current time and 3 lines: done, now, next.
3. `git add -A`
4. Commit:
   - check OK: `git commit -m "checkpoint <HH:MM>: <one-line summary>"`
   - check FAIL: `git commit -m "wip <HH:MM>: <summary>, check red: <reason>"`
     A red checkpoint is still required. Never skip the hourly commit.
5. `git push`. If push fails because of auth or a remote change, show the exact error and the one
   command the user should run. Never force-push, never rewrite history.
6. Reply in Russian, 3 lines max: commit hash, check status, next checkpoint time (HH:50).

## Context hygiene
If the session has been running for more than about 90 minutes, recommend: "Откройте новую сессию
Codex. Первым сообщением: прочитай AGENTS.md и docs/progress.md, продолжаем с <next>."

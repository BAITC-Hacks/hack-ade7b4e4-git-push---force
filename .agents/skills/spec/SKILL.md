---
name: spec
description: Turn the HackAlem case into a one-page spec with a demo path, requirements, edge cases, acceptance tests and work units. Use at the start of the hackathon, when the user pastes the case, runs $spec, or says "разбери кейс" or "напиши спеку". Planning only, no code.
---

# spec (hackathon mode)

Turn the case into a spec precise enough that `$build` can implement it without guessing.
Hackathon mode: you have 15 minutes, not an afternoon. The discipline stays, the interview shrinks.

## The one rule that matters most: do not build
While this skill is active you are a requirements analyst. No code, no scaffolding, no file edits
except `specs/solution.md` and `docs/progress.md`. Building early defeats the point.
Safety invariants of the case (for example "a risky action needs a human") go into the spec as
requirements with a test, so `$build` puts them in `app/guardrails.py`, not only in the prompt.

## Step 1: read the case
- Source: the text the user pasted, or `docs/CASE.md`. If both are empty, ask for the case and stop.
- The track has several cases and the team solves ONE. If more than one case is pasted, compare them in
  5 lines (fit to the kit, mandatory requirements doable in 5 hours, clarity of criteria) and ask which one.
- Read `.agents/skills/fintech/SKILL.md` and map the case to the closest pattern.
- Extract: who gave the case, who the end user is, the pain, what data is given, how the case says it will be judged.

## Step 2: choose narrow
Propose ONE user, ONE pain, ONE golden path: the 3-6 steps a judge will click through in the demo.
Everything else goes to non-goals. A narrow path that works beats five features on slides.

## Step 3: ask, at most 3 questions, one at a time
Only questions whose answer changes what gets built. Each question comes with your recommended
default, so the user can answer "да" in one word. If the user says "решай сам", use your defaults
and record them under Assumptions. Do not batch questions.

## Step 4: write specs/solution.md (in Russian)
Use this template. Every requirement and done-criterion must be checkable.

```markdown
# <Название решения>

## Цель
Для кого, какая боль, какой результат. 2-4 предложения. Почему это важно партнёру кейса.

## Демо-сценарий (golden path)
1. Пользователь ... 2. Агент ... 3. Экран показывает ...
(Это и есть сценарий показа жюри. 3-6 шагов.)

## Требования
- R1 [обяз.] ... (каждое обязательное требование кейса отдельным пунктом, проверяемо: вход, выход, где видно)
- R2 ...

## Ограничения и не-цели
- Стек: FastAPI + static UI из репозитория, OpenAI API через app/llm.py, деплой на Vercel.
- Только синтетические данные. 5 часов.
- Не-цели: ...

## Крайние случаи
- E1 Нет данных по клиенту: ...
- E2 Попытка обойти правила (prompt injection): ...
- E3 Сообщение на казахском: ...
- E4 Ключ API не работает: демо-кэш отвечает на сценарии показа.

## Готово, когда
- [ ] Все требования с пометкой [обяз.] работают
- [ ] Основной сценарий от входных данных до результата проверен
- [ ] A1 <приёмочный тест шага 1 демо-сценария>
- [ ] A2 <...>
- [ ] A3 <...>
- [ ] python scripts/check.py зелёный, python scripts/smoke.py OK
- [ ] README по структуре организаторов, решение сдано на платформе («Сдать решение»)
- [ ] Ссылка открывается, демо-сценарий проходит на ней (если деплоим)
- [ ] evals: не меньше 15 кейсов, точность не ниже 80%

## Юниты работы
- [ ] U1 ЦЕЛЬ: ... | ГДЕ: 2-3 файла | НЕЛЬЗЯ: ... | ГОТОВО: какой тест или команда
- [ ] U2 ...
(4-7 юнитов, каждый не больше 40 минут. Первый юнит всегда: адаптировать app/agent.py под кейс.)

## Допущения
- ...

## Открытые вопросы
- ... (только если что-то осталось нерешённым)
```

Unit order that works: U1 agent + schema, U2 tools and data for the case, U3 UI for the golden path,
U4 edge cases and guardrails, U5 evals, U6 deploy and demo cache.

## Step 5: finish
- Write 3 lines to `docs/progress.md`: done, now, next.
- Commit the case and the spec so judges see them in history:
  `git add docs/CASE.md specs/solution.md docs/progress.md` then `git commit -m "spec: <название решения>"`.
- Reply with: the golden path in one line, the unit list, and "Дальше: $build U1".
- Stop. Building is a separate action the user starts.

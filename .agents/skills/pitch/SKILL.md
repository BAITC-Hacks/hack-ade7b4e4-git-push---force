---
name: pitch
description: Write the final README and a 3-minute pitch (5 slides, demo script, likely jury questions) strictly from facts in the repo. Use when the user runs $pitch, asks "сделай презентацию", "README", "что сказать жюри", or at feature freeze (16:30).
---

# pitch

Judges see two things: the repo and the demo. Both must tell the same story with real numbers.

## The one rule that matters most: facts only
Every number comes from the repo: `evals/results.json`, `logs/usage.jsonl`, `/api/stats`,
`specs/solution.md`, `git log --oneline | wc -l`. If a number is missing, write "нет данных" and
say which command produces it. Never invent users, savings, percentages or quotes.

## Step 1: collect
Read: `docs/CASE.md`, `specs/solution.md`, `evals/results.json`, `app/agent.py` (tools, schema),
`app/tools.py` (tool names), `docs/progress.md`, the README link line and its "Раскрытие" section.

## Step 2: README.md (Russian, keep the section order of the template)
The organizers require these points: what the project does and for whom, what is implemented,
how it works (main scenario from input to result), technologies, architecture, install and run,
how to check it (a scenario the jury can repeat), data and external services, limitations,
the deployed link if any. The template in README.md already follows that order: fill every section.
If `docs/CASE.md` contains the organizers' README prompt, follow it as well; it wins over this file.
"Архитектура" maps the product to the 6 harness blocks the organizers published (context, tools,
memory, model routing, interaction logic, monitoring). "Как проверить" must be steps a judge can
repeat locally or on the link, with the expected result. "Ограничения" is honest: what is not done.
Keep sections 11-13 (metrics, how we worked with the AI agent, disclosure).

## Step 3: docs/PITCH.md (Russian)
- 5 slides, max 25 words each: Проблема (с цифрой и источником) / Демо / Как работает (6 блоков) /
  Метрики (точность, доля быстрой модели, стоимость запроса в тенге, задержка) / Пилот (кто, какие данные, какая метрика).
- Demo script: 3 minutes, which button to press, what to say while the model answers, the Kazakh
  scenario, the prompt-injection scenario, the "Что ушло в модель" reveal.
- Plan B: if the network dies, the same prompts answer from the demo cache (DEMO badge).
- 5 likely jury questions with 2-sentence answers (security, cost at scale, why not one big model,
  what data the pilot needs, what is pre-made vs built today).

## Step 4: text for the submission form (docs/PITCH.md, section "Сдача")
The team submits on the platform: tracks page, the case, «Сдать решение», name and description.
Write: a name up to 60 characters and a description of 3-4 sentences (problem, what works, link).
Remind the team: submit a first version by 16:45 and update it before the deadline.

## Style
Short declarative sentences. No em dashes. No hype words. Russian.

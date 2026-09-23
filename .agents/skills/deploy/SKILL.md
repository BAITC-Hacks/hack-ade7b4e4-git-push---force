---
name: deploy
description: Put the app on a public Vercel link that keeps working during judging, with the demo cache warmed and a smoke test against the live URL. Use when the user runs $deploy, asks "задеплой", "нужна ссылка", or the link is broken.
---

# deploy (Vercel, from the local folder, no Git connection needed)

The rules require a working link for the whole review period 24-28.09 (8.7-8.9).
Deploy early (first hour, even an empty app), then redeploy after each milestone.
The organizers' README asks for the deployed link "if it exists": not mandatory, but judges check faster with it.
Never put keys in the repo: they live in `.env` locally and in Vercel settings.

## Pre-flight (all must pass)
1. `python scripts/check.py` OK and `python scripts/smoke.py` OK.
2. `.env` is NOT tracked: `git ls-files .env` prints nothing.
3. If the demo path works live: `python scripts/warm_cache.py`, then commit `data/demo_cache.json`.

## First deploy
Steps 1-3 are interactive. The human runs them in their own terminal, not through Codex.
1. `npx vercel@latest login`
2. In the repo folder: `npx vercel@latest link` (create a new project, accept the defaults).
3. Keys: Vercel dashboard -> the project -> Settings -> Environment Variables -> add
   `OPENAI_API_KEY` for Production. Models and other settings come from the defaults in
   `app/config.py`; add an env var only to override one of them.
Then you (Codex) run, asking for network approval:
4. `npx vercel@latest deploy --prod --yes`
   If it fails on login or the sandbox, give the human this exact command for their terminal.
5. Take the PRODUCTION domain `https://<project>.vercel.app` from the output ("Aliased" line) or
   the dashboard. Do NOT hand judges the long generated URL: Standard Protection makes it ask for a
   Vercel login. Open the production domain in a private window to be sure.

## After every deploy
- `python scripts/smoke.py --url https://<project>.vercel.app` must print SMOKE OK.
- The health endpoint `/api/health` shows `"mode": "live"`. If it says demo, the env var is missing:
  add it and redeploy (env changes need a new deploy).
- Put the link at the top of README.md and in `docs/progress.md`. Commit.

## When it breaks
- Build fails: `npx vercel@latest deploy --prod --yes --logs` and read the first error line.
- 500 on /api/ask: `npx vercel@latest logs https://<project>.vercel.app`.
- Page asks to log in: wrong URL (generated one) or protection on. Use the production domain, or
  Settings -> Deployment Protection -> turn Vercel Authentication off.
- Timeouts: raise `maxDuration` in `vercel.json` (60 is set) or lower MAX_OUTPUT_TOKENS_SMART.
- Module not found: the package is missing in `requirements.txt`.
Fallback host: `Dockerfile` works on Render or any VPS (`uvicorn app.main:app --port $PORT`).

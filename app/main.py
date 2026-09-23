"""FastAPI entry point. Local: python -m uvicorn app.main:app --reload
Vercel finds `app` in app/main.py automatically.
"""
from __future__ import annotations

import sys
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # makes `from app import ...` work however the host loads us
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app import agent, config, data, llm  # noqa: E402

app = FastAPI(title=config.APP_TITLE)

_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


def _rate_limited(request: Request) -> bool:
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0]
    now = time.time()
    with _hits_lock:
        q = _hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= config.RATE_LIMIT_PER_MIN:
            return True
        q.append(now)
    return False


class AskIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    client_id: str | None = Field(default=None, max_length=64)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "mode": llm.mode(),
        "models": {"fast": config.MODEL_FAST, "smart": config.MODEL_SMART},
        "title": config.APP_TITLE,
    }


@app.get("/api/meta")
def meta() -> dict:
    return {
        "title": config.APP_TITLE,
        "mode": llm.mode(),
        "usd_kzt": config.USD_KZT,
        "demo_prompts": data.demo_prompts(),
        "models": {"fast": config.MODEL_FAST, "smart": config.MODEL_SMART},
    }


@app.post("/api/ask")
def ask(body: AskIn, request: Request) -> dict:
    if _rate_limited(request):
        raise HTTPException(status_code=429, detail="Слишком много запросов, подождите минуту")
    answer, info = agent.ask(body.message, body.client_id)
    return {"answer": answer.model_dump(), "meta": info}


@app.get("/api/stats")
def stats() -> dict:
    return llm.stats()


@app.get("/api/clients")
def clients() -> list[dict]:
    return data.clients()[:100]


# Keep this last: API routes above win over static files.
app.mount("/", StaticFiles(directory=str(config.STATIC_DIR), html=True), name="ui")

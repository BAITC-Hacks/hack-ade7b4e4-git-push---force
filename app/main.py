"""FastAPI chat and read-only graph API. Servers are started by the user."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app import assistant, config
from app.graph_store import GraphStore


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Введите вопрос")
        return value.strip()


def create_app(graph_path: str | Path | None = None) -> FastAPI:
    path = Path(graph_path or os.getenv("GRAPH_JSON", str(config.ROOT / "out" / "graph.json")))
    hits: dict[str, deque] = defaultdict(deque)
    lock = threading.Lock()

    def load_graph(application: FastAPI) -> None:
        try:
            application.state.graph = GraphStore.from_file(path)
        except (OSError, ValueError):
            application.state.graph = None

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        load_graph(application)
        yield

    application = FastAPI(title="Граф денег — ассистент аналитика", lifespan=lifespan)
    application.state.graph = None

    def graph() -> GraphStore:
        # A pipeline export may arrive after startup; retry only if missing.
        if application.state.graph is None:
            with lock:
                if application.state.graph is None:
                    load_graph(application)
        if application.state.graph is None:
            raise HTTPException(503, "Граф пока недоступен. Дождитесь выгрузки данных командой.")
        return application.state.graph

    @application.get("/")
    def index():
        return FileResponse(config.STATIC_DIR / "index.html")

    @application.get("/api/health")
    def health():
        try:
            store = graph()
        except HTTPException:
            store = None
        return {"ok": store is not None, "graph_available": store is not None,
                "n_nodes": len(store.nodes) if store else 0,
                "n_edges": len(store.edges) if store else 0, "llm_enabled": assistant.llm_enabled()}

    @application.get("/api/top")
    def top(n: int = Query(10, ge=1, le=100)):
        return graph().top_nodes(n)

    @application.post("/api/ask")
    def ask(body: AskIn, request: Request):
        store = graph()
        rate_limit(request)
        answer, info = assistant.ask(body.question, store)
        return public_answer(answer, info)

    def rate_limit(request: Request) -> None:
        ip = request.client.host if request.client else "local"
        now = time.monotonic()
        with lock:
            expired = [key for key, queue in hits.items() if not queue or now - queue[-1] >= 60]
            for key in expired:
                del hits[key]
            queue = hits[ip]
            while queue and now - queue[0] >= 60:
                queue.popleft()
            if len(queue) >= config.RATE_LIMIT_PER_MIN:
                raise HTTPException(429, "Слишком много запросов. Подождите минуту.")
            queue.append(now)

    def public_answer(answer: assistant.AssistantAnswer, info: dict) -> dict:
        public_meta = {key: info[key] for key in ("mode", "tier", "model", "latency_ms", "cost_usd")
                       if key in info}
        public_meta["removed_gid_count"] = len(info.get("guardrails", []))
        return {**answer.model_dump(), "tools": info.get("tools", []), "meta": public_meta}

    @application.get("/api/node/{gid}")
    def node(gid: str, direction: Literal["in", "out", "both"] = "both"):
        store = graph()
        if gid not in store.nodes:
            raise HTTPException(404, "Узел не найден в текущем графе")
        result = store.neighbors(gid, direction=direction, limit=100)
        return {**result, "viewer_url": assistant.viewer_url(gid)}

    @application.get("/api/card/{gid}")
    def card(gid: str):
        store = graph()
        if gid not in store.nodes:
            raise HTTPException(404, "Узел не найден в текущем графе")
        try:
            return assistant.get_card(gid, store)
        except LookupError:
            raise HTTPException(404, "Готовая карточка узла отсутствует в графе") from None

    @application.get("/api/draft/{gid}")
    def draft(gid: str, request: Request):
        store = graph()
        if gid not in store.nodes:
            raise HTTPException(404, "Узел не найден в текущем графе")
        rate_limit(request)
        try:
            answer, info = assistant.get_draft(gid, store)
        except LookupError:
            raise HTTPException(404, "Готовая карточка узла отсутствует в графе") from None
        return {**public_answer(answer, info), "gid": gid, "draft": answer.answer,
                "viewer_url": assistant.viewer_url(gid)}

    @application.get("/viewer")
    def viewer():
        viewer_path = path.parent / "viewer.html"
        if not viewer_path.is_file():
            raise HTTPException(404, "Схема ещё не подготовлена командой")
        return FileResponse(viewer_path, media_type="text/html")

    application.mount("/static", StaticFiles(directory=config.STATIC_DIR, check_dir=False), name="static")
    return application


app = create_app()

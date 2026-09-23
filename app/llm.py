"""LLM gateway: the only module that talks to OpenAI.

run_structured() does, in order:
  1. masks personal data (app/pii.py)
  2. picks a tier, fast or smart, and records why (app/router.py)
  3. returns a memory-cache hit if the same request was answered already
  4. calls the model with tools + Structured Outputs (Responses API)
  5. escalates a low-confidence fast answer to the smart tier
  6. counts tokens, cost and latency, logs them to logs/usage.jsonl
Any error (no key, bad model name, rate limit, budget spent) falls back to the
demo cache (data/demo_cache.json) or a safe stub, so the public link keeps working.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Type, TypeVar

from pydantic import BaseModel

from app import config
from app import tools as toolbox
from app.pii import mask_pii
from app.router import Route, choose_tier

T = TypeVar("T", bound=BaseModel)

DEMO_CACHE_PATH = config.DATA_DIR / "demo_cache.json"

_lock = threading.Lock()
_client: Any = None
_memory_cache: dict[str, tuple[dict, dict]] = {}
_stats: dict[str, Any] = {}


def reset_state() -> None:
    """Clear caches and counters (used by tests and scripts)."""
    _memory_cache.clear()
    _stats.clear()
    _stats.update(
        requests=0, live=0, fast=0, smart=0, escalations=0, demo=0, fallback=0,
        memory_hits=0, spent_usd=0.0, latency_ms_total=0,
    )


reset_state()


def get_client() -> Any:
    global _client
    if _client is None:
        from openai import OpenAI

        kwargs: dict[str, Any] = {
            "api_key": config.OPENAI_API_KEY or "missing",
            "timeout": config.OPENAI_TIMEOUT,
            "max_retries": 2,
        }
        if config.OPENAI_BASE_URL:
            kwargs["base_url"] = config.OPENAI_BASE_URL
        _client = OpenAI(**kwargs)
    return _client


def set_client(client: Any) -> None:
    """Tests inject a fake client here."""
    global _client
    _client = client


def mode() -> str:
    if config.DEMO_MODE == "on":
        return "demo"
    if config.DEMO_MODE != "off" and not config.OPENAI_API_KEY:
        return "demo"
    if _stats["spent_usd"] >= config.BUDGET_USD:
        return "demo"
    return "live"


def cost_usd(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float | None:
    price = config.price_for(model)
    if price is None:
        return None
    p_in, p_cached, p_out = price
    uncached = max(0, input_tokens - cached_tokens)
    return round((uncached * p_in + cached_tokens * p_cached + output_tokens * p_out) / 1_000_000, 6)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower()).strip(" .!?")


def load_demo_cache() -> dict:
    try:
        return json.loads(DEMO_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_demo_entry(masked_text: str, answer: dict, meta: dict) -> None:
    cache = load_demo_cache()
    keep = ("model", "tier", "route_reason", "input_tokens", "cached_tokens", "output_tokens",
            "cost_usd", "latency_ms", "tools_called", "escalated")
    cache[normalize(masked_text)] = {"answer": answer, "meta": {k: meta.get(k) for k in keep}}
    DEMO_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def run_structured(
    *,
    instructions: str,
    user_text: str,
    schema: Type[T],
    stub: Callable[[str], T],
    tools: list[str] | None = None,
    task: str = "answer",
    force_tier: str | None = None,
) -> tuple[T, dict]:
    """Main entry point. Returns (parsed answer, meta for UI and logs)."""
    t0 = time.perf_counter()
    masked, pii = mask_pii(user_text)
    route = Route(force_tier, "tier задан вручную", 0) if force_tier else choose_tier(task, masked)
    meta: dict[str, Any] = {
        "mode": mode(),
        "tier": route.tier,
        "route_reason": route.reason,
        "pii_masked": pii,
        "sent_to_model": masked,
        "calls": [],
        "tools_called": [],
        "cache": None,
        "escalated": False,
        "error": None,
        "model": None,
    }

    if meta["mode"] == "demo":
        return _from_demo(masked, schema, stub, meta, t0)

    key = _cache_key(route.tier, instructions, masked, schema, tools)
    hit = _memory_cache.get(key)
    if hit:
        answer, old = hit
        meta.update(cache="memory", tools_called=old["tools_called"], model=old["model"],
                    tier=old["tier"], escalated=old["escalated"])
        return schema.model_validate(answer), _finish(meta, t0)

    try:
        parsed, call = _call(route.tier, instructions, masked, schema, tools)
        meta["calls"].append(call)
        if route.tier == "fast" and not force_tier and _confidence(parsed) < config.ESCALATE_BELOW:
            parsed, call2 = _call("smart", instructions, masked, schema, tools)
            meta["calls"].append(call2)
            meta["escalated"] = True
            meta["tier"] = "smart"
            meta["route_reason"] += f"; эскалация: уверенность быстрой модели ниже {config.ESCALATE_BELOW}"
    except Exception as exc:  # never crash the demo
        meta["mode"] = "fallback"
        meta["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        return _from_demo(masked, schema, stub, meta, t0)

    for c in meta["calls"]:
        meta["tools_called"].extend(c["tools_called"])
    meta["model"] = meta["calls"][-1]["model"]
    finished = _finish(meta, t0)
    _memory_cache[key] = (parsed.model_dump(), copy.deepcopy(finished))
    return parsed, finished


def stats() -> dict:
    with _lock:
        s = dict(_stats)
    answered = s["fast"] + s["smart"]
    s["share_fast_pct"] = round(100 * s["fast"] / answered, 1) if answered else None
    s["avg_latency_ms"] = round(s["latency_ms_total"] / s["requests"]) if s["requests"] else None
    s["mode"] = mode()
    s["budget_usd"] = config.BUDGET_USD
    return s


# ---------------- internals ----------------


def _call(tier: str, instructions: str, text: str, schema: Type[T], tool_names: list[str] | None) -> tuple[T, dict]:
    model = config.MODEL_SMART if tier == "smart" else config.MODEL_FAST
    effort = config.REASONING_SMART if tier == "smart" else config.REASONING_FAST
    max_out = config.MAX_OUTPUT_TOKENS_SMART if tier == "smart" else config.MAX_OUTPUT_TOKENS_FAST

    client = get_client()
    tool_defs = toolbox.openai_tools(tool_names)
    base: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "text_format": schema,
        "max_output_tokens": max_out,
    }
    if tool_defs:
        base["tools"] = tool_defs
    if effort:
        base["reasoning"] = {"effort": effort}

    started = time.perf_counter()
    usage = {"input": 0, "cached": 0, "output": 0}
    called: list[dict] = []

    response = client.responses.parse(input=[{"role": "user", "content": text}], **base)
    rounds = 1
    while True:
        _add_usage(usage, response)
        fcalls = [o for o in (getattr(response, "output", None) or []) if getattr(o, "type", None) == "function_call"]
        if not fcalls or rounds > config.MAX_TOOL_ROUNDS:
            break
        outputs = []
        for fc in fcalls:
            result = toolbox.call_tool(fc.name, fc.arguments)
            called.append({"name": fc.name, "arguments": _safe_json(fc.arguments), "result": result})
            outputs.append({
                "type": "function_call_output",
                "call_id": fc.call_id,
                "output": json.dumps(result, ensure_ascii=False),
            })
        extra = {"tool_choice": "none"} if rounds >= config.MAX_TOOL_ROUNDS else {}
        response = client.responses.parse(input=outputs, previous_response_id=response.id, **base, **extra)
        rounds += 1

    if getattr(response, "status", "completed") == "incomplete":
        raise RuntimeError(f"ответ модели неполный: {getattr(response, 'incomplete_details', None)}")
    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        raw = getattr(response, "output_text", "") or ""
        if not raw:
            raise RuntimeError("модель не вернула ответ (возможен отказ или лимит токенов)")
        parsed = schema.model_validate_json(raw)

    return parsed, {
        "tier": tier,
        "model": model,
        "rounds": rounds,
        "input_tokens": usage["input"],
        "cached_tokens": usage["cached"],
        "output_tokens": usage["output"],
        "cost_usd": cost_usd(model, usage["input"], usage["cached"], usage["output"]),
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "tools_called": called,
    }


def _from_demo(masked: str, schema: Type[T], stub: Callable[[str], T], meta: dict, t0: float) -> tuple[T, dict]:
    entry = load_demo_cache().get(normalize(masked))
    if entry:
        saved = entry.get("meta") or {}
        meta["cache"] = "demo"
        meta["cached_meta"] = saved
        meta["tools_called"] = saved.get("tools_called") or []
        meta["model"] = saved.get("model")
        meta["tier"] = saved.get("tier") or meta["tier"]
        meta["escalated"] = bool(saved.get("escalated"))
        if saved.get("route_reason"):
            meta["route_reason"] = f"сохранённый ответ; {saved['route_reason']}"
        answer = schema.model_validate(entry["answer"])
    else:
        meta["cache"] = "stub"
        answer = stub(masked)
    return answer, _finish(meta, t0)


def _finish(meta: dict, t0: float) -> dict:
    calls = meta["calls"]
    meta["input_tokens"] = sum(c["input_tokens"] for c in calls)
    meta["cached_tokens"] = sum(c["cached_tokens"] for c in calls)
    meta["output_tokens"] = sum(c["output_tokens"] for c in calls)
    costs = [c["cost_usd"] for c in calls if c["cost_usd"] is not None]
    if not calls:
        meta["cost_usd"] = 0.0
    else:
        meta["cost_usd"] = round(sum(costs), 6) if len(costs) == len(calls) else None
    meta["cost_kzt"] = (
        round(meta["cost_usd"] * config.USD_KZT, 2) if config.USD_KZT and meta["cost_usd"] is not None else None
    )
    meta["latency_ms"] = int((time.perf_counter() - t0) * 1000)

    with _lock:
        _stats["requests"] += 1
        _stats["latency_ms_total"] += meta["latency_ms"]
        if meta["mode"] == "demo":
            _stats["demo"] += 1
        elif meta["mode"] == "fallback":
            _stats["fallback"] += 1
        else:
            _stats["live"] += 1
            if meta["cache"] == "memory":
                _stats["memory_hits"] += 1
            _stats["smart" if meta["tier"] == "smart" else "fast"] += 1
            if meta["escalated"]:
                _stats["escalations"] += 1
            _stats["spent_usd"] = round(_stats["spent_usd"] + (meta["cost_usd"] or 0.0), 6)
    _log(meta)
    return meta


def _add_usage(acc: dict, response: Any) -> None:
    u = getattr(response, "usage", None)
    if not u:
        return
    acc["input"] += getattr(u, "input_tokens", 0) or 0
    details = getattr(u, "input_tokens_details", None)
    acc["cached"] += (getattr(details, "cached_tokens", 0) or 0) if details else 0
    acc["output"] += getattr(u, "output_tokens", 0) or 0


def _confidence(parsed: BaseModel) -> float:
    value = getattr(parsed, "confidence", 1.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def _cache_key(tier: str, instructions: str, text: str, schema: type, tools: list[str] | None) -> str:
    raw = json.dumps([tier, config.MODEL_FAST, config.MODEL_SMART, instructions, text, schema.__name__, tools],
                     ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_json(arguments: Any) -> Any:
    if isinstance(arguments, str):
        try:
            return json.loads(arguments)
        except Exception:
            return arguments
    return arguments


def _log(meta: dict) -> None:
    """Append one line per request. Silently skipped on read-only hosts (Vercel)."""
    try:
        config.LOG_DIR.mkdir(exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **{k: meta.get(k) for k in ("mode", "tier", "model", "cache", "escalated", "input_tokens",
                                        "cached_tokens", "output_tokens", "cost_usd", "latency_ms", "error")},
            "tools": [t["name"] for t in meta.get("tools_called", [])],
        }
        with open(config.LOG_DIR / "usage.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass

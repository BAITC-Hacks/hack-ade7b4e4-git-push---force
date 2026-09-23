"""Smoke test of the running app.

    python scripts/smoke.py                 # in-process, demo mode, no network
    python scripts/smoke.py --url https://your-app.vercel.app   # deployed link

Checks /api/health, /api/meta and one /api/ask. Prints OK or the failing step.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # UTF-8 output on Windows too (Codex reads it)
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run(get, post) -> int:
    h = get("/api/health")
    assert h.status_code == 200 and h.json()["ok"], f"health: {h.status_code} {h.text[:200]}"
    m = get("/api/meta")
    assert m.status_code == 200, f"meta: {m.status_code}"
    prompts = m.json().get("demo_prompts") or [{"message": "Проверь операцию T-DEMO-1", "client_id": "C-DEMO-1"}]
    p = prompts[0]
    a = post("/api/ask", {"message": p["message"], "client_id": p.get("client_id")})
    assert a.status_code == 200, f"ask: {a.status_code} {a.text[:300]}"
    body = a.json()
    assert body["answer"]["answer"], "пустой ответ"
    ui = get("/")
    assert ui.status_code == 200 and "<html" in ui.text.lower(), f"UI: {ui.status_code}"
    print(f"SMOKE OK · mode={h.json()['mode']} · cache={body['meta'].get('cache')} · "
          f"model={body['meta'].get('model')} · {body['meta'].get('latency_ms')} мс")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="адрес задеплоенного приложения")
    args = ap.parse_args()
    try:
        if args.url:
            import httpx

            base = args.url.rstrip("/")
            with httpx.Client(timeout=90, follow_redirects=True) as c:
                return run(lambda p: c.get(base + p), lambda p, j: c.post(base + p, json=j))
        os.environ.setdefault("DEMO_MODE", "on")
        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as c:
            return run(c.get, lambda p, j: c.post(p, json=j))
    except AssertionError as exc:
        print(f"SMOKE FAIL: {exc}")
        return 1
    except Exception as exc:
        print(f"SMOKE FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

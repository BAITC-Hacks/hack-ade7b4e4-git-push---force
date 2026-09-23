"""Save live answers for the demo prompts into data/demo_cache.json.

    python scripts/warm_cache.py

Run it once the demo scenario works, with a real key. Commit the file. If the
key stops working during judging (24-28.09), these prompts still answer
from the cache and the public link keeps working.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import agent, data, llm  # noqa: E402

for _stream in (sys.stdout, sys.stderr):  # UTF-8 output on Windows too (Codex reads it)
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    if llm.mode() != "live":
        print("Нужен живой режим: задайте OPENAI_API_KEY в .env и уберите DEMO_MODE=on.")
        return 1
    ok = 0
    for p in data.demo_prompts():
        answer, meta = agent.ask(p["message"], p.get("client_id"))
        if meta["mode"] != "live":
            print(f"FAIL {p['title']}: {meta.get('error')}")
            continue
        llm.save_demo_entry(meta["sent_to_model"], answer.model_dump(), meta)
        ok += 1
        print(f"OK   {p['title']} · {meta['model']} · ${meta.get('cost_usd')} · {meta['latency_ms']} мс")
    print(f"Сохранено {ok} из {len(data.demo_prompts())} в data/demo_cache.json. Закоммитьте файл.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

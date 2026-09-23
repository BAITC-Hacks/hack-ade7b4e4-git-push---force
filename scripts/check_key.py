"""Check the OpenAI key and the configured models. Run first thing on 23.09.

    python scripts/check_key.py

Prints which models the key can see and makes one tiny call per configured
tier (MODEL_FAST, MODEL_SMART) with its latency and cost.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.llm import cost_usd  # noqa: E402

for _stream in (sys.stdout, sys.stderr):  # UTF-8 output on Windows too (Codex reads it)
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main() -> int:
    if not config.OPENAI_API_KEY:
        print("Нет OPENAI_API_KEY. Создайте файл .env со строкой OPENAI_API_KEY=ваш_ключ.")
        return 1
    from openai import OpenAI

    kwargs = {"api_key": config.OPENAI_API_KEY, "timeout": 60}
    if config.OPENAI_BASE_URL:
        kwargs["base_url"] = config.OPENAI_BASE_URL
    client = OpenAI(**kwargs)

    try:
        ids = sorted(m.id for m in client.models.list())
        family = [i for i in ids if i.startswith(("gpt-6", "gpt-5", "o"))]
        print(f"Ключ работает. Доступно моделей: {len(ids)}")
        print("Похожие на нужные: " + (", ".join(family[:40]) or "нет"))
    except Exception as exc:
        print(f"Список моделей не получен: {type(exc).__name__}: {exc}")

    failed = False
    for tier, model in (("fast", config.MODEL_FAST), ("smart", config.MODEL_SMART)):
        started = time.perf_counter()
        try:
            r = client.responses.create(model=model, input="Ответь одним словом: готово", max_output_tokens=400)
            ms = int((time.perf_counter() - started) * 1000)
            u = r.usage
            cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
            price = cost_usd(model, u.input_tokens, cached, u.output_tokens)
            print(f"OK {tier}: {model} · {ms} мс · {u.input_tokens}+{u.output_tokens} токенов · "
                  f"${price if price is not None else 'цена неизвестна'} · ответ: {r.output_text.strip()[:40]!r}")
        except Exception as exc:
            failed = True
            print(f"FAIL {tier}: {model} · {type(exc).__name__}: {str(exc)[:200]}")
            print(f"   Поменяйте MODEL_{tier.upper()} в app/config.py на модель из списка выше.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

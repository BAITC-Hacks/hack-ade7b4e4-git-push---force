"""Публикует AI-ассистента на Vercel отдельным проектом graf-deneg-ai.

    python scripts/deploy_ai.py            # собрать deploy/graf-deneg-ai и опубликовать
    python scripts/deploy_ai.py --dry-run  # только собрать папку

В папку попадают только app/, static/, out/graph.json и out/viewer.html и короткий requirements.txt
(без pandas и scipy: ассистенту они не нужны, а размер функции на Vercel ограничен).
Ключ OpenAI читается из .env и передаётся Vercel флагом --env только этому деплою.
На экран и в git он не попадает. Без ключа ассистент работает в режиме без модели.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "deploy" / "graf-deneg-ai"
ENV_KEYS = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "MODEL_FAST", "MODEL_SMART")
# Замер на Vercel: ответ быстрой модели с инструментами занимал около 15 с. Низкое усилие рассуждения
# ускоряет ответ, общий лимит 40 с покрывает раунды инструментов и эскалацию. Значения из .env важнее.
DEPLOY_DEFAULTS = {"REASONING_FAST": "low", "REASONING_SMART": "low", "OPENAI_TOTAL_TIMEOUT": "40"}
REQUIREMENTS = ["fastapi>=0.115", "openai>=2.0", "pydantic>=2.7", "python-dotenv>=1.0", "httpx>=0.27"]
VERCEL_JSON = {"functions": {"app/main.py": {"maxDuration": 60, "includeFiles": "{static,out}/**"}}}


def build() -> None:
    for sub in ("app", "static", "out"):
        shutil.rmtree(DST / sub, ignore_errors=True)
        (DST / sub).mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "app").glob("*.py"):
        shutil.copy2(f, DST / "app" / f.name)
    for f in (ROOT / "static").iterdir():
        if f.is_file():
            shutil.copy2(f, DST / "static" / f.name)
    for name in ("graph.json", "viewer.html"):
        src = ROOT / "out" / name
        if not src.is_file():
            sys.exit(f"Нет {src}. Сначала: python -m pipeline --data data --out out")
        shutil.copy2(src, DST / "out" / name)
    (DST / "requirements.txt").write_text("\n".join(REQUIREMENTS) + "\n", encoding="utf-8")
    (DST / "vercel.json").write_text(json.dumps(VERCEL_JSON, indent=2) + "\n", encoding="utf-8")
    print(f"Папка собрана: {DST}")


def env_flags() -> list[str]:
    try:
        from dotenv import dotenv_values
    except ImportError:
        print("python-dotenv не установлен: публикую без модели.")
        return []
    values = dotenv_values(ROOT / ".env")
    flags = []
    for key in ENV_KEYS:
        if values.get(key):
            flags += ["--env", f"{key}={values[key]}"]
    for key, default in DEPLOY_DEFAULTS.items():
        flags += ["--env", f"{key}={values.get(key) or default}"]
    names = [k for k in ENV_KEYS if values.get(k)]
    print("Переменные для Vercel: " + (", ".join(names) if names else "нет, ассистент будет работать без модели"))
    return flags


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    build()
    if args.dry_run:
        return 0
    if not (shutil.which("npx") or shutil.which("npx.cmd")):
        sys.exit("Не найден npx. Нужен Node.js.")
    parts = ["npx", "--yes", "vercel@latest", "deploy", str(DST.relative_to(ROOT)), "--prod", "--yes", *env_flags()]
    if os.name == "nt":
        return subprocess.run(subprocess.list2cmdline(parts), cwd=ROOT, shell=True).returncode
    return subprocess.run(parts, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())

"""Fast project check with short output (for people and for Codex).

    python scripts/check.py

Compiles all Python files and runs the tests. Prints one summary line and the
first failure. Full output goes to logs/check.log. Exit code 0 means green.
Never start the web server as a check: it does not exit and hangs the agent.
"""
from __future__ import annotations

import compileall
import os
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # UTF-8 output on Windows too (Codex reads it)
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "check.log"


def main() -> int:
    os.chdir(ROOT)
    LOG.parent.mkdir(exist_ok=True)
    ok = all(compileall.compile_dir(str(ROOT / d), quiet=1) for d in ("app", "scripts", "tests", "data"))
    if not ok:
        print("FAIL: синтаксическая ошибка, см. вывод выше")
        return 1
    env = {**os.environ, "DEMO_MODE": "on", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-W", "ignore::DeprecationWarning", "tests"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    out = proc.stdout + proc.stderr
    LOG.write_text(out, encoding="utf-8")
    lines = [ln for ln in out.splitlines() if ln.strip()]
    summary = next((ln for ln in reversed(lines) if " passed" in ln or " failed" in ln or " error" in ln), "")
    if proc.returncode == 0:
        print(f"OK {summary.strip('= ')}")
        return 0
    first = next((ln for ln in lines if ln.startswith(("E ", "FAILED", "ERROR"))), "")
    print(f"FAIL {summary.strip('= ')}")
    if first:
        print(first[:300])
    print(f"подробно: {LOG.relative_to(ROOT)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

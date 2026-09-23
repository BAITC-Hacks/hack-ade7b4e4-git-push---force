"""python -m pipeline --data data --out out"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):  # кириллица в консоли Windows
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

from .run import run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline",
                                 description="Граф денег: роли, кластеры и приоритеты узлов из трёх parquet.")
    ap.add_argument("--data", default="data", help="папка с edges.parquet, nodes.parquet, transactions.parquet")
    ap.add_argument("--out", default="out", help="куда писать выгрузки")
    ap.add_argument("--no-viewer", action="store_true", help="не собирать out/viewer.html")
    ap.add_argument("--core", action="store_true",
                    help="только роли, кластеры, приоритет и три CSV (для очень больших графов)")
    a = ap.parse_args()
    run(Path(a.data), Path(a.out), build_viewer=not a.no_viewer, core_only=a.core)
    return 0


if __name__ == "__main__":
    sys.exit(main())

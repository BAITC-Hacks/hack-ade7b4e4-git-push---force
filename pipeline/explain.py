"""Объяснить роль узла за минуту: python -m pipeline.explain <gid> [--out out]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.explain")
    ap.add_argument("gid", nargs="+", help="один или несколько gid")
    ap.add_argument("--out", default="out", help="папка с graph.json")
    a = ap.parse_args()
    g = json.loads((Path(a.out) / "graph.json").read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in g["nodes"]}
    for gid in a.gid:
        n = nodes.get(str(gid).strip())
        if not n:
            print(f"{gid}: такого узла в графе нет\n")
            continue
        print(f"=== {gid} ===")
        print(n["card"])
        print(f"Обоснование роли: {n['evidence']}")
        if n.get("why"):
            reasons = n["why"].split("Почему в топе:", 1)
            print(f"Место в топе: №{n['rank']}. {reasons[1].strip() if len(reasons) > 1 else n['why']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

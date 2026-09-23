"""Assemble an offline HTML document without third-party Python dependencies."""

import argparse
import json
import math
import re
from pathlib import Path


def _validate(graph: dict) -> None:
    ids = [node["id"] for node in graph["nodes"]]
    if any(not isinstance(gid, str) or not gid for gid in ids):
        raise ValueError("Node gids must be nonempty strings")
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate node gid")
    known = set(ids)
    for node in graph["nodes"]:
        for field in ("x", "y", "priority_score"):
            if not isinstance(node[field], (int, float)) or not math.isfinite(node[field]):
                raise ValueError(f"Invalid {field} for {node['id']}")
    for edge in graph["edges"]:
        if edge["source"] not in known or edge["target"] not in known:
            raise ValueError("Edge endpoints must be known string gids")
    for item in graph["top"]:
        if item["gid"] not in known:
            raise ValueError("Top entries must reference known string gids")
    for cluster in graph["clusters"]:
        if any(gid not in known for gid in cluster["top_gids"]):
            raise ValueError("Cluster top_gids must reference known string gids")


def build_viewer(graph_json: Path, out_html: Path) -> None:
    """Embed graph, vendored vis-network, styles and application into one HTML."""
    root = Path(__file__).resolve().parent
    graph = json.loads(Path(graph_json).read_text(encoding="utf-8"))
    _validate(graph)
    # Prevent data from terminating the script element, even in evidence/why.
    data = json.dumps(graph, ensure_ascii=False, allow_nan=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    vendor = (root / "vendor" / "vis-network.min.js").read_text(encoding="utf-8")
    vendor = re.sub(r"//# sourceMappingURL=.*", "", vendor)
    parts = {
        "STYLE": (root / "style.css").read_text(encoding="utf-8"),
        "VENDOR": vendor,
        "GRAPH": data,
        "APP": (root / "what_if.js").read_text(encoding="utf-8") + "\n" + (root / "app.js").read_text(encoding="utf-8"),
    }
    template = (root / "template.html").read_text(encoding="utf-8")
    html = re.sub(r"@@(STYLE|VENDOR|GRAPH|APP)@@", lambda match: parts[match[1]], template)
    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Собрать автономный экран AML-аналитика")
    parser.add_argument("--graph", type=Path, default=Path("out/graph.json"))
    parser.add_argument("--out", type=Path, default=Path("out/viewer.html"))
    args = parser.parse_args()
    build_viewer(args.graph, args.out)
    print(f"Viewer: {args.out}")


if __name__ == "__main__":
    main()

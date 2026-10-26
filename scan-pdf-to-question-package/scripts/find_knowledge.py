#!/usr/bin/env python3
"""Return compact knowledge-point candidates for one question batch."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def find_candidates(keywords: list[str], limit: int = 40) -> list[dict[str, str]]:
    catalog_path = Path(__file__).resolve().parent.parent / "references" / "knowledge_points.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    normalized = [item.strip().lower() for item in keywords if item.strip()]
    scored: list[tuple[int, int, dict[str, str]]] = []
    for index, item in enumerate(payload["entries"]):
        path_text = " ".join(str(item.get(key, "")) for key in ("level_1", "level_2", "level_3")).lower()
        helper_text = " ".join(
            str(item.get(key, "")) for key in ("typical_question", "applicable_grade", "default_difficulty")
        ).lower()
        score = sum(4 for keyword in normalized if keyword in path_text)
        score += sum(1 for keyword in normalized if keyword in helper_text)
        if score:
            scored.append(
                (
                    -score,
                    index,
                    {
                        "level_1": item["level_1"],
                        "level_2": item["level_2"],
                        "level_3": item["level_3"],
                    },
                )
            )
    scored.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in scored[:limit]]


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python find_knowledge.py 关键词1 [关键词2 ...]")
        return 2
    print(json.dumps(find_candidates(sys.argv[1:]), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

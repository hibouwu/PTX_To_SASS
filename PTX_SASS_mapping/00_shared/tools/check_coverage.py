#!/usr/bin/env python3
"""Report observed levels and pair coverage for dotted paths in a JSONL manifest."""

from __future__ import annotations

import argparse
import itertools
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def resolve(record: dict[str, Any], path: str) -> Any:
    value: Any = record
    for component in path.split("."):
        if not isinstance(value, dict) or component not in value:
            return "<MISSING>"
        value = value[component]
    return json.dumps(value, sort_keys=True, ensure_ascii=False) if isinstance(value, (dict, list)) else value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--factor", action="append", required=True, help="dotted record path; repeat for multiple factors")
    args = parser.parse_args()
    records = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    levels: dict[str, set[Any]] = defaultdict(set)
    pairs: dict[tuple[str, str], set[tuple[Any, Any]]] = defaultdict(set)
    for record in records:
        values = {factor: resolve(record, factor) for factor in args.factor}
        for factor, value in values.items():
            levels[factor].add(value)
        for left, right in itertools.combinations(args.factor, 2):
            pairs[(left, right)].add((values[left], values[right]))
    print(json.dumps({"record_count": len(records), "levels": {factor: {"count": len(values), "values": sorted(values, key=str)} for factor, values in levels.items()}, "pairs": {f"{left} x {right}": {"observed": len(values), "naive_cartesian": len(levels[left]) * len(levels[right])} for (left, right), values in pairs.items()}}, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

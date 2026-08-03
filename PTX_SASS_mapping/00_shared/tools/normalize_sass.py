#!/usr/bin/env python3
"""Normalize physical SASS register numbers while preserving classes and aliases."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REGISTER_PATTERN = re.compile(r"(?<![A-Za-z0-9_])(UR|UP|R|P)(\d+)(?![A-Za-z0-9_])")


def normalize_text(text: str) -> str:
    mappings: dict[str, dict[str, str]] = {register_class: {} for register_class in ("R", "UR", "P", "UP")}

    def replace(match: re.Match[str]) -> str:
        register_class = match.group(1)
        physical_name = match.group(0)
        class_mapping = mappings[register_class]
        if physical_name not in class_mapping:
            class_mapping[physical_name] = f"{register_class}{{{len(class_mapping)}}}"
        return class_mapping[physical_name]

    return REGISTER_PATTERN.sub(replace, text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="read stdin when omitted")
    args = parser.parse_args()
    if not args.files:
        sys.stdout.write(normalize_text(sys.stdin.read()))
        return 0
    for index, path in enumerate(args.files):
        if index:
            sys.stdout.write("\n")
        sys.stdout.write(normalize_text(path.read_text(encoding="utf-8")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

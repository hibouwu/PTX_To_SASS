#!/usr/bin/env python3
"""Validate the common structural contract of PTX-to-SASS JSONL manifests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "case_label": str,
    "kernel": str,
    "semantic_form": dict,
    "semantic_form_id": str,
    "target_instructions": list,
    "target_occurrence_count": int,
    "validation_scope": str,
}
VALIDATION_SCOPES = {"STATIC_ASSEMBLY_ONLY", "STATIC_ATTRIBUTION", "RUNTIME_SEMANTIC", "RUNTIME_PROTOCOL"}


def load_records(path: Path) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, 1):
            if not raw_line.strip():
                continue
            try:
                value = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: record must be an object")
            records.append((line_number, value))
    return records


def validate_record(path: Path, line_number: int, record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in record:
            errors.append(f"{path}:{line_number}: missing required field {field}")
        elif not isinstance(record[field], expected_type) or expected_type is int and isinstance(record[field], bool):
            errors.append(f"{path}:{line_number}: {field} must be {expected_type.__name__}")
    if isinstance(record.get("case_label"), str) and not record["case_label"]:
        errors.append(f"{path}:{line_number}: case_label must not be empty")
    if isinstance(record.get("kernel"), str) and not record["kernel"]:
        errors.append(f"{path}:{line_number}: kernel must not be empty")
    if isinstance(record.get("target_instructions"), list) and (not record["target_instructions"] or not all(isinstance(item, str) and item for item in record["target_instructions"])):
        errors.append(f"{path}:{line_number}: target_instructions must contain non-empty strings")
    if isinstance(record.get("target_occurrence_count"), int) and record["target_occurrence_count"] < 1:
        errors.append(f"{path}:{line_number}: target_occurrence_count must be positive")
    if record.get("validation_scope") not in VALIDATION_SCOPES:
        errors.append(f"{path}:{line_number}: unknown validation_scope {record.get('validation_scope')!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    args = parser.parse_args()
    errors: list[str] = []
    seen_labels: dict[str, tuple[Path, int]] = {}
    record_count = 0
    for path in args.manifests:
        try:
            records = load_records(path)
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        record_count += len(records)
        for line_number, record in records:
            errors.extend(validate_record(path, line_number, record))
            label = record.get("case_label")
            if isinstance(label, str):
                if label in seen_labels:
                    previous_path, previous_line = seen_labels[label]
                    errors.append(f"{path}:{line_number}: duplicate case_label {label!r}; first seen at {previous_path}:{previous_line}")
                else:
                    seen_labels[label] = (path, line_number)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"validated {record_count} records across {len(args.manifests)} manifest(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

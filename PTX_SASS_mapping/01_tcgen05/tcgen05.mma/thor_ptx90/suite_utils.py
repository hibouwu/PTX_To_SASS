#!/usr/bin/env python3
"""Shared safety and identity helpers for the Thor tcgen05 test suite."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


OWNER_MARKER = ".tcgen05-suite-owner.json"


def stable_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _validate_reset_target(path: Path, protected: tuple[Path, ...]) -> Path:
    resolved = path.expanduser().resolve()
    filesystem_root = Path(resolved.anchor)
    if resolved == filesystem_root or len(resolved.parts) < 3:
        raise SystemExit(f"error: refusing unsafe output directory: {resolved}")

    current = Path.cwd().resolve()
    protected_paths = (current, *[item.resolve() for item in protected])
    for item in protected_paths:
        if resolved == item or resolved in item.parents:
            raise SystemExit(
                "error: refusing to reset current/protected directory or its "
                f"ancestor: {resolved}"
            )
    return resolved


def reset_owned_directory(
    path: Path, *, owner: str, protected: tuple[Path, ...] = ()
) -> Path:
    """Create a clean suite-owned directory without deleting unowned content."""

    resolved = _validate_reset_target(path, protected)
    marker = resolved / OWNER_MARKER
    if resolved.exists():
        if not resolved.is_dir():
            raise SystemExit(
                f"error: output path exists and is not a directory: {resolved}"
            )
        if not marker.is_file():
            raise SystemExit(
                f"error: refusing to delete unowned directory without {OWNER_MARKER}: "
                f"{resolved}"
            )
        try:
            marker_data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(
                f"error: invalid ownership marker in {resolved}"
            ) from error
        if marker_data.get("owner") != owner:
            raise SystemExit(
                f"error: directory owner mismatch for {resolved}: "
                f"expected {owner!r}, found {marker_data.get('owner')!r}"
            )
        shutil.rmtree(resolved)

    resolved.mkdir(parents=True)
    (resolved / OWNER_MARKER).write_text(
        json.dumps(
            {"schema_version": "tcgen05_suite_owner_v1", "owner": owner},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    resolved = _validate_reset_target(
        args.path, (Path(__file__).resolve().parent,)
    )
    print(resolved)


if __name__ == "__main__":
    main()

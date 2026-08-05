#!/usr/bin/env python3
"""Audit family directories for adversarial-review deliverable completeness.

Usage: python3 audit_families.py <family_dir> [<family_dir> ...]

Static checks only (no compilation):
1. 实验设计.md exists and mentions the review-checklist anchors
   (校准/实测, 负向/诊断, 补集, template, STATIC_ONLY).
2. At least one <opcode>/thor_ptx90/ suite with suite_spec.py + suite_runtime.py
   + check_all.sh + validation summaries, all validation_status == PASS.
3. suite_spec.py declares expected_diagnostic probes and a complement/补集 marker.
4. Family README no longer claims NOT_STARTED.

Exit code 0 only if every audited family passes all checks.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

DESIGN_ANCHORS = {
    "实测校准": re.compile(r"实测|校准"),
    "负向诊断": re.compile(r"诊断|expected_diagnostic"),
    "补集抽样": re.compile(r"补集"),
    "模板受控": re.compile(r"template_wide|模板"),
    "STATIC_ONLY": re.compile(r"STATIC_ONLY"),
}


def audit_suite(suite: Path) -> list[str]:
    problems = []
    for name in ("suite_spec.py", "suite_runtime.py", "check_all.sh"):
        if not (suite / name).is_file():
            problems.append(f"缺 {name}")
    spec_path = suite / "suite_spec.py"
    if spec_path.is_file():
        spec = spec_path.read_text(encoding="utf-8")
        if "expected_diagnostic" not in spec:
            problems.append("suite_spec.py 无 expected_diagnostic 锚定")
        if "补集" not in spec and "complement" not in spec:
            problems.append("suite_spec.py 无补集抽样标记")
    validation = suite / "validation"
    summaries = sorted(validation.glob("*.json")) if validation.is_dir() else []
    if not summaries:
        problems.append("无 validation/*.json（套件未跑通）")
    for summary in summaries:
        try:
            data = json.loads(summary.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            problems.append(f"{summary.name} 非法 JSON")
            continue
        status = data.get("validation_status")
        if status is not None and status != "PASS":
            problems.append(f"{summary.name} 状态 {status}")
    return problems


def audit_family(family: Path) -> tuple[bool, list[str]]:
    notes = []
    ok = True
    design = family / "实验设计.md"
    if not design.is_file():
        return False, ["缺 实验设计.md"]
    text = design.read_text(encoding="utf-8")
    for label, pattern in DESIGN_ANCHORS.items():
        if not pattern.search(text):
            ok = False
            notes.append(f"实验设计.md 缺检查单锚点：{label}")
    readme = family / "README.md"
    if readme.is_file() and "NOT_STARTED" in readme.read_text(encoding="utf-8"):
        ok = False
        notes.append("README 仍为 NOT_STARTED")
    suites = sorted(family.glob("*/thor_ptx90"))
    validated = []
    for suite in suites:
        problems = audit_suite(suite)
        if problems:
            notes.append(f"{suite.parent.name}: " + "；".join(problems))
        else:
            validated.append(suite.parent.name)
    if not validated:
        ok = False
        notes.append("没有任何全绿套件")
    else:
        notes.append("全绿套件：" + "、".join(validated))
    return ok, notes


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    overall = True
    for arg in sys.argv[1:]:
        family = Path(arg)
        ok, notes = audit_family(family)
        overall = overall and ok
        print(f"{'PASS' if ok else 'FAIL'} {family.name}")
        for note in notes:
            print(f"  - {note}")
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())

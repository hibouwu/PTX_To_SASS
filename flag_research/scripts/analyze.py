#!/usr/bin/env python3
"""Summarize nvdisasm output from the O0..O3 PTXAS experiment."""

from __future__ import annotations

import csv
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path


SASS_LINE = re.compile(
    r"/\*[0-9a-fA-F]+\*/\s+((?:@\S+\s+)?)([A-Z][A-Z0-9_.]*)\b(.*?)\s*;"
)
IGNORE = {"NOP", "EXIT"}


def instructions(path: Path) -> tuple[list[str], list[str]]:
    ops: list[str] = []
    normalized: list[str] = []
    for line in path.read_text(errors="replace").splitlines():
        match = SASS_LINE.search(line)
        if match:
            predicate, mnemonic, operands = match.groups()
            if mnemonic.split(".")[0] not in IGNORE:
                ops.append(mnemonic)
                text = f"{predicate}{mnemonic}{operands}"
                normalized.append(" ".join(text.split()))
    return ops, normalized


def marker_result(case: str, ops: list[str], normalized: list[str]) -> str:
    bases = [op.split(".")[0] for op in ops]
    if case in {"06_fma_contract", "07_fma_blocked_rounding"}:
        found = sum(base in {"FFMA", "FMAD", "DFMA"} for base in bases)
        return f"FMAx{found}" if found else "none"
    if case == "08_integer_imad":
        # IMAD.MOV is parameter setup, not evidence for source mul+add fusion.
        imad = sum(op == "IMAD" for op in ops)
        iadd = sum(base == "IADD3" for base in bases)
        return f"IMADx{imad}/IADD3x{iadd}"
    if case == "09_boolean_lop3":
        count = sum(base == "LOP3" for base in bases)
        return f"LOP3x{count}"
    if case == "10_shift_add_lea":
        lea = sum(base == "LEA" for base in bases)
        shift = sum(base == "SHF" for base in bases)
        return f"LEAx{lea}/SHFx{shift}"
    if case == "11_load_address_fold":
        folded = sum(
            op.split(".")[0] == "LDG" and "+0x10]" in text
            for op, text in zip(ops, normalized)
        )
        return "LDG+0x10" if folded else "separate-address-add"
    return ""


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: analyze.py RESULTS_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    sass_dir = root / "sass"
    paths = sorted(sass_dir.glob("*.sass"))
    if not paths:
        print(f"ERROR: no .sass files under {sass_dir}", file=sys.stderr)
        return 1

    rows: list[dict[str, str | int]] = []
    name_re = re.compile(r"(.+)_(baseline|fmad_off)_O([0-3])$")
    for path in paths:
        match = name_re.fullmatch(path.stem)
        if not match:
            continue
        case, profile, level = match.groups()
        ops, normalized = instructions(path)
        counts = Counter(ops)
        normalized_text = " | ".join(normalized)
        rows.append(
            {
                "case": case,
                "profile": profile,
                "level": int(level),
                "instruction_count": len(ops),
                "fusion_marker": marker_result(case, ops, normalized),
                "mnemonics": " ".join(ops),
                "histogram": " ".join(f"{op}:{counts[op]}" for op in sorted(counts)),
                "sass_sha256": hashlib.sha256(normalized_text.encode()).hexdigest()[:16],
                "normalized_sass": normalized_text,
            }
        )

    rows.sort(key=lambda row: (str(row["case"]), str(row["profile"]), int(row["level"])))
    fieldnames = [
        "case",
        "profile",
        "level",
        "instruction_count",
        "fusion_marker",
        "mnemonics",
        "histogram",
        "sass_sha256",
        "normalized_sass",
    ]
    with (root / "sass_matrix.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    baseline = [row for row in rows if row["profile"] == "baseline"]
    cases = sorted({str(row["case"]) for row in baseline})
    lines = [
        "# PTXAS O0–O3 experiment report",
        "",
        "Generated from the exact cubins and nvdisasm dumps in this directory.",
        "Instruction counts exclude `NOP` and `EXIT`, but retain setup, memory,",
        "control-flow, and return instructions. Compare mnemonic sequences before",
        "drawing conclusions from counts alone.",
        "",
        "## Baseline matrix",
        "",
        "| case | O0 | O1 | O2 | O3 | first mnemonic change | full-SASS changes | fusion evidence by level |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ]
    for case in cases:
        case_rows = sorted(
            (row for row in baseline if row["case"] == case),
            key=lambda row: int(row["level"]),
        )
        by_level = {int(row["level"]): row for row in case_rows}
        first_mnemonic_change = "none"
        for level in range(1, 4):
            if by_level[level]["mnemonics"] != by_level[level - 1]["mnemonics"]:
                first_mnemonic_change = f"O{level - 1}->O{level}"
                break
        full_changes = ", ".join(
            f"O{level - 1}->O{level}"
            for level in range(1, 4)
            if by_level[level]["normalized_sass"]
            != by_level[level - 1]["normalized_sass"]
        ) or "none"
        counts = [str(by_level[level]["instruction_count"]) for level in range(4)]
        markers = ", ".join(
            f"O{level}:{by_level[level]['fusion_marker'] or '-'}" for level in range(4)
        )
        lines.append(
            f"| `{case}` | {' | '.join(counts)} | {first_mnemonic_change} | "
            f"{full_changes} | {markers} |"
        )

    fma_rows = [
        row
        for row in rows
        if row["case"] == "06_fma_contract" and row["profile"] == "fmad_off"
    ]
    if fma_rows:
        lines.extend(
            [
                "",
                "## FMA semantic control (`-fmad=false`)",
                "",
                "| level | instruction count | fusion marker | mnemonics |",
                "|---|---:|---|---|",
            ]
        )
        for row in sorted(fma_rows, key=lambda item: int(item["level"])):
            lines.append(
                f"| O{row['level']} | {row['instruction_count']} | "
                f"{row['fusion_marker']} | `{row['mnemonics']}` |"
            )

    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "- These observations apply to the recorded PTXAS version and target architecture.",
            "- An unchanged mnemonic sequence does not prove identical scheduling or encodings;",
            "  inspect the corresponding `.sass` files for operands and control codes.",
            "- `full-SASS changes` compares predicates, opcodes, and operands after removing",
            "  only instruction addresses and whitespace. It can expose changes hidden by",
            "  identical mnemonic sequences.",
            "- `FFMA`, `IMAD`, `LOP3`, `LEA`, and a folded LDG offset are instruction-selection",
            "  evidence. They may appear even at O0 because PTX is a virtual ISA and PTXAS",
            "  must still lower it.",
            "- A fusion marker says the target SASS opcode appeared; use the negative/control",
            "  cases to decide whether it came from the intended source pattern.",
            "",
        ]
    )
    (root / "report.md").write_text("\n".join(lines))
    print(f"Analyzed {len(rows)} disassemblies into {root / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

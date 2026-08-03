#!/usr/bin/env python3
"""Verify that known non-Thor tcgen05 modifiers are rejected by ptxas."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from generate_cases import Case, Step, render_kernel
from suite_utils import reset_owned_directory


ROOT = Path(__file__).resolve().parent
PROBES = (
    (
        "scale_input_d",
        Case("mma", 1, "f16", "smem_descriptor", None, 0, False, "probe", (Step(),), "runtime_zero"),
        r"scale-inp-d-imm.*not supported.*sm_110a",
    ),
    (
        "block_scale_with_ashift",
        Case("mma", 1, "mxf8f6f4", "tmem_address", "scale_vec::1X", None, False, "probe", (Step(ashift=True),), "runtime_zero"),
        r"Illegal modifier '.ashift'.*tcgen05\.mma",
    ),
    (
        "smem_descriptor_with_ashift",
        Case("mma", 1, "tf32", "smem_descriptor", None, None, False, "probe", (Step(ashift=True),), "runtime_zero"),
        r"Illegal modifier '.ashift'.*tcgen05\.mma",
    ),
    (
        "ws_cta_group_2",
        Case("mma.ws", 2, "f16", "smem_descriptor", None, None, False, "probe", (Step(),), "runtime_zero"),
        r"cta_group::2|Illegal modifier|Arguments mismatch",
    ),
    (
        "normal_uses_b_collector",
        Case("mma", 1, "f16", "smem_descriptor", None, None, False, "probe", (Step("fill", "b0"),), "runtime_zero"),
        r"collector::b0|Illegal modifier|Arguments mismatch",
    ),
    (
        "ws_uses_a_collector",
        Case("mma.ws", 1, "f16", "smem_descriptor", None, None, False, "probe", (Step("fill", "a"),), "runtime_zero"),
        r"collector::a|Illegal modifier|Arguments mismatch",
    ),
    (
        "mxf4nvf4_omits_scale_vector",
        Case("mma", 1, "mxf4nvf4", "smem_descriptor", None, None, False, "probe", (Step(),), "runtime_zero"),
        r"scale_vec|Illegal modifier|Arguments mismatch",
    ),
    (
        "mxf8f6f4_scale_vec_2x",
        Case("mma", 1, "mxf8f6f4", "smem_descriptor", "scale_vec::2X", None, False, "probe", (Step(),), "runtime_zero"),
        r"scale_vec::2X|Illegal modifier|Arguments mismatch",
    ),
    (
        "mxf4_scale_vec_1x",
        Case("mma", 1, "mxf4", "smem_descriptor", "scale_vec::1X", None, False, "probe", (Step(),), "runtime_zero"),
        r"scale_vec::1X|Illegal modifier|Arguments mismatch",
    ),
    (
        "ws_block_scale",
        Case("mma.ws", 1, "mxf4", "smem_descriptor", "scale_vec::2X", None, False, "probe", (Step(),), "runtime_zero"),
        r"block_scale|Illegal modifier|Arguments mismatch",
    ),
    (
        "cta_group_3",
        Case("mma", 3, "f16", "smem_descriptor", None, None, False, "probe", (Step(),), "runtime_zero"),
        r"cta_group::3|Illegal modifier|Arguments mismatch",
    ),
)


def error_diagnostics(stderr: str) -> list[dict]:
    records = []
    for line in stderr.splitlines():
        match = re.search(r", line ([0-9]+); error\s+: (.*)$", line)
        if match:
            records.append(
                {"line": int(match.group(1)), "message": match.group(2).strip()}
            )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ptxas", type=Path, default=Path("/usr/local/cuda/bin/ptxas"))
    parser.add_argument(
        "--work-dir", type=Path, default=ROOT / "results" / "negative-probes"
    )
    parser.add_argument("--summary-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    work_dir = reset_owned_directory(
        args.work_dir,
        owner="thor_tcgen05_negative_probes",
        protected=(ROOT,),
    )

    results = []
    for ordinal, (name, case, expected_diagnostic_pattern) in enumerate(PROBES, start=1):
        source = work_dir / f"probe_{ordinal:03d}.ptx"
        cubin = work_dir / f"probe_{ordinal:03d}.cubin"
        source_text = "\n".join(
            (
                ".version 9.0",
                ".target sm_110a",
                ".address_size 64",
                f'.file 1 "probe_{ordinal:03d}.ptx"',
                "",
                render_kernel(case, ordinal),
            )
        )
        source.write_text(source_text, encoding="utf-8")
        target_lines = [
            line_number
            for line_number, line in enumerate(source_text.splitlines(), start=1)
            if "tcgen05.mma" in line and not line.lstrip().startswith("//")
        ]
        if len(target_lines) != 1:
            raise RuntimeError(
                f"{name}: expected exactly one target occurrence, got {target_lines}"
            )
        command = [
            str(args.ptxas),
            "-arch=sm_110a",
            "-O0",
            str(source),
            "-o",
            str(cubin),
        ]
        completed = subprocess.run(command, text=True, capture_output=True)
        diagnostics = error_diagnostics(completed.stderr)
        passed = completed.returncode != 0 and any(
            item["line"] == target_lines[0]
            and re.search(expected_diagnostic_pattern, item["message"])
            for item in diagnostics
        )
        results.append(
            {
                "probe": name,
                "expected": "PTXAS_REJECT",
                "expected_diagnostic_pattern": expected_diagnostic_pattern,
                "expected_error_line": target_lines[0],
                "returncode": completed.returncode,
                "parsed_error_diagnostics": diagnostics,
                "diagnostic": completed.stderr.strip().splitlines(),
                "status": "PASS" if passed else "FAIL",
            }
        )
        print(f"{'PASS' if passed else 'FAIL'} expected rejection: {name}")

    ptxas_version = subprocess.run(
        [str(args.ptxas), "--version"], text=True, capture_output=True, check=True
    ).stdout
    report = {
        "schema_version": "thor_tcgen05_negative_probe_summary_v2",
        "validation_status": (
            "PASS" if all(result["status"] == "PASS" for result in results) else "FAIL"
        ),
        "ptx_isa": "9.0",
        "ptx_target": "sm_110a",
        "ptxas_sha256": hashlib.sha256(args.ptxas.read_bytes()).hexdigest(),
        "ptxas_version": ptxas_version.strip().splitlines(),
        "probe_count": len(results),
        "expected_rejection_pass_count": sum(
            result["status"] == "PASS" for result in results
        ),
        "results": results,
    }
    report_path = work_dir / "negative_probe_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"report: {report_path}")
    if report["validation_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Compile CTX.protocol and effect-slice cases at O0/O1/O2/O3."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from suite_utils import reset_owned_directory
from validate_generated import validate_directory


ROOT = Path(__file__).resolve().parent
OPTIMIZATIONS = ("O0", "O1", "O2", "O3")


def compile_one(ptxas: Path, source: Path, output: Path, optimization: str) -> dict:
    completed = subprocess.run(
        [
            str(ptxas),
            "-arch=sm_110a",
            f"-{optimization}",
            str(source),
            "-o",
            str(output),
        ],
        text=True,
        capture_output=True,
    )
    output_exists = output.is_file()
    output_size = output.stat().st_size if output_exists else 0
    return {
        "source": source.name,
        "layer": source.parent.name,
        "optimization": optimization,
        "returncode": completed.returncode,
        "stderr": completed.stderr,
        "output": output.name,
        "output_exists": output_exists,
        "output_size": output_size,
        "artifact_valid": completed.returncode == 0 and output_size > 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--ptxas", type=Path, default=Path("/usr/local/cuda/bin/ptxas")
    )
    parser.add_argument(
        "--nvdisasm", type=Path, default=Path("/usr/local/cuda/bin/nvdisasm")
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=ROOT / "results" / "protocol-layers",
    )
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()
    if args.jobs < 1:
        raise SystemExit("--jobs must be positive")
    work_dir = reset_owned_directory(
        args.work_dir, owner="thor_tcgen05_protocol_check", protected=(ROOT,)
    )
    source_dir = work_dir / "sources"
    cubin_dir = work_dir / "cubins"
    cubin_dir.mkdir(parents=True)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "generate_protocol_layers.py"),
            "--output",
            str(source_dir),
        ],
        check=True,
    )
    source_validation = validate_directory(source_dir)
    generation = json.loads(
        (source_dir / "summary.json").read_text(encoding="utf-8")
    )
    sources = sorted(source_dir.glob("*/*.ptx"))
    if not sources or len(sources) != generation["case_count"]:
        raise RuntimeError("protocol source set is empty or differs from summary")
    jobs = [
        (
            source,
            cubin_dir / f"{source.parent.name}_{source.stem}_{optimization}.cubin",
            optimization,
        )
        for source in sources
        for optimization in OPTIMIZATIONS
    ]
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        pending = {
            executor.submit(compile_one, args.ptxas, source, output, optimization)
            for source, output, optimization in jobs
        }
        for future in as_completed(pending):
            result = future.result()
            results.append(result)
            status = "PASS" if result["artifact_valid"] else "FAIL"
            print(
                f"{status} {result['layer']}/{result['source']} "
                f"{result['optimization']}"
            )
    results.sort(
        key=lambda item: (item["layer"], item["source"], item["optimization"])
    )
    compile_failures = [item for item in results if not item["artifact_valid"]]
    sass_checks = []
    for result in results:
        if not result["artifact_valid"] or result["layer"] != "effect_slice":
            continue
        disassembly = subprocess.run(
            [str(args.nvdisasm), str(cubin_dir / result["output"])],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        required = [
            "UTCHMMA",
            "UTCBAR",
            "SYNCS.PHASECHK",
            "LDTM",
            "UVIRTCOUNT.DEALLOC.SMPOOL",
        ]
        if "_st_wait_" in result["source"]:
            required.append("STTM")
        missing = [pattern for pattern in required if pattern not in disassembly]
        sass_checks.append(
            {
                "source": result["source"],
                "optimization": result["optimization"],
                "required_patterns": required,
                "missing_patterns": missing,
                "status": "PASS" if not missing else "FAIL",
            }
        )
    sass_failures = [item for item in sass_checks if item["status"] != "PASS"]
    expected_sass_checks = (
        generation["layer_case_counts"]["effect_slice"] * len(OPTIMIZATIONS)
    )
    if len(sass_checks) != expected_sass_checks:
        raise RuntimeError(
            f"SASS check count mismatch: expected {expected_sass_checks}, "
            f"got {len(sass_checks)}"
        )
    ptxas_version = subprocess.run(
        [str(args.ptxas), "--version"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip().splitlines()
    summary = {
        "schema_version": "thor_tcgen05_protocol_compile_summary_v2",
        "validation_status": (
            "PASS" if not compile_failures and not sass_failures else "FAIL"
        ),
        "generation": generation,
        "optimizations": list(OPTIMIZATIONS),
        "ptxas_sha256": hashlib.sha256(args.ptxas.read_bytes()).hexdigest(),
        "ptxas_version": ptxas_version,
        "compile_attempt_count": len(results),
        "compile_pass_count": len(results) - len(compile_failures),
        "compile_failure_count": len(compile_failures),
        "source_validation": source_validation,
        "sass_check_count": len(sass_checks),
        "sass_check_pass_count": len(sass_checks) - len(sass_failures),
        "compile_failures": compile_failures,
        "sass_failures": sass_failures,
    }
    report_path = work_dir / "compile_report.json"
    report_path.write_text(
        json.dumps(
            {**summary, "results": results, "sass_checks": sass_checks},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if args.summary_output is not None:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        f"{summary['compile_pass_count']}/{summary['compile_attempt_count']} "
        f"compile attempts passed; report: {report_path}"
    )
    if compile_failures or sass_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

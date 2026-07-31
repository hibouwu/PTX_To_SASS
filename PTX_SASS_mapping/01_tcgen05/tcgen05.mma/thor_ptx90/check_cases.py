#!/usr/bin/env python3
"""Generate and compile Thor tcgen05.mma shards with CUDA 13 ptxas."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from extract_core_sass import extract_suite
from suite_utils import reset_owned_directory
from validate_generated import validate_directory


ROOT = Path(__file__).resolve().parent


def compile_one(ptxas: Path, source: Path, output: Path, opt: str) -> dict:
    command = [
        str(ptxas),
        "-arch=sm_110a",
        f"-{opt}",
        str(source),
        "-o",
        str(output),
    ]
    started = time.monotonic()
    result = subprocess.run(command, text=True, capture_output=True)
    output_exists = output.is_file()
    output_size = output.stat().st_size if output_exists else 0
    return {
        "source": source.name,
        "optimization": opt,
        "returncode": result.returncode,
        "seconds": round(time.monotonic() - started, 4),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "output": output.name,
        "output_exists": output_exists,
        "output_size": output_size,
        "artifact_valid": result.returncode == 0 and output_size > 0,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("syntax", "expanded"), default="syntax")
    parser.add_argument(
        "--optimizations",
        nargs="+",
        choices=("O0", "O1", "O2", "O3"),
        default=("O0", "O1", "O2", "O3"),
        help="ptxas optimization levels (default: all four levels)",
    )
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--shard-size", type=int, default=64)
    parser.add_argument("--ptxas", type=Path, default=Path("/usr/local/cuda/bin/ptxas"))
    parser.add_argument(
        "--nvdisasm", type=Path, default=Path("/usr/local/cuda/bin/nvdisasm")
    )
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="optional compact, repository-safe validation summary",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.jobs < 1:
        raise SystemExit("--jobs must be positive")
    requested_work_dir = args.work_dir or ROOT / "results" / args.mode
    work_dir = reset_owned_directory(
        requested_work_dir, owner="thor_tcgen05_mma_check", protected=(ROOT,)
    )
    source_dir = work_dir / "sources"
    cubin_dir = work_dir / "cubins"
    cubin_dir.mkdir(parents=True)

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "generate_cases.py"),
            "--mode",
            args.mode,
            "--shard-size",
            str(args.shard_size),
            "--output",
            str(source_dir),
        ],
        check=True,
    )

    source_validation = validate_directory(source_dir)
    generated_summary = json.loads(
        (source_dir / "summary.json").read_text(encoding="utf-8")
    )
    sources = sorted(source_dir.glob("*.ptx"))
    if not sources or len(sources) != generated_summary["source_shard_count"]:
        raise RuntimeError("generated source set is empty or differs from summary")
    jobs = []
    for source in sources:
        for opt in args.optimizations:
            jobs.append(
                (
                    source,
                    cubin_dir / f"{source.stem}_{opt}.cubin",
                    opt,
                )
            )

    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        pending = {
            executor.submit(compile_one, args.ptxas, source, output, opt): (
                source,
                opt,
            )
            for source, output, opt in jobs
        }
        for future in as_completed(pending):
            result = future.result()
            results.append(result)
            status = "PASS" if result["artifact_valid"] else "FAIL"
            print(f"{status} {result['source']} {result['optimization']}")

    results.sort(key=lambda item: (item["source"], item["optimization"]))
    failures = [result for result in results if not result["artifact_valid"]]
    sass_target_attribution = extract_suite(
        source_dir=source_dir,
        cubin_dir=cubin_dir,
        output_dir=work_dir / "sass",
        nvdisasm=args.nvdisasm,
        optimizations=args.optimizations,
        jobs=args.jobs,
    )
    ptxas_version = subprocess.run(
        [str(args.ptxas), "--version"], text=True, capture_output=True, check=True
    ).stdout
    report = {
        "schema_version": "thor_tcgen05_mma_compile_report_v3",
        "mode": args.mode,
        "ptx_target": "sm_110a",
        "ptxas_path": str(args.ptxas),
        "ptxas_sha256": hashlib.sha256(args.ptxas.read_bytes()).hexdigest(),
        "ptxas_version": ptxas_version,
        "source_shard_count": len(sources),
        "compile_attempt_count": len(results),
        "compile_pass_count": len(results) - len(failures),
        "compile_failure_count": len(failures),
        "source_validation": source_validation,
        "sass_target_attribution": sass_target_attribution,
        "results": results,
    }
    report_path = work_dir / "compile_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if args.summary_output is not None:
        compact_sass_attribution = {
            key: value
            for key, value in sass_target_attribution.items()
            if key
            not in {
                "nvdisasm_path",
                "raw_sass_directory",
                "liveness_sass_directory",
                "attribution_file",
            }
        }
        compact = {
            "schema_version": "thor_tcgen05_mma_compile_summary_v3",
            "validation_status": (
                "PASS"
                if not failures and sass_target_attribution["status"] == "COMPLETE"
                else "FAIL"
            ),
            "generation": generated_summary,
            "optimizations": list(args.optimizations),
            "ptxas_sha256": report["ptxas_sha256"],
            "ptxas_version": ptxas_version.strip().splitlines(),
            "source_shard_count": len(sources),
            "compile_attempt_count": len(results),
            "compile_pass_count": len(results) - len(failures),
            "compile_failure_count": len(failures),
            "source_validation": source_validation,
            "sass_target_attribution": compact_sass_attribution,
        }
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(
            json.dumps(compact, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        f"{report['compile_pass_count']}/{report['compile_attempt_count']} "
        f"compile attempts passed; report: {report_path}"
    )
    if failures or sass_target_attribution["status"] != "COMPLETE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

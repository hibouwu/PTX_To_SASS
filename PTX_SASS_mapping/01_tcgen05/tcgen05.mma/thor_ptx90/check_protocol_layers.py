#!/usr/bin/env python3
"""Compile CTX.protocol and effect-slice cases at O0/O1/O2/O3."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from suite_utils import reset_owned_directory
from validate_generated import validate_directory


ROOT = Path(__file__).resolve().parent
OPTIMIZATIONS = ("O0", "O1", "O2", "O3")


INSTRUCTION_RE = re.compile(r"/\*[0-9a-f]+\*/\s+(.*?)\s*;", re.IGNORECASE)


def operations(disassembly: str) -> list[str]:
    return [match.group(1).strip() for match in INSTRUCTION_RE.finditer(disassembly)]


def ordered_match(ops: list[str], patterns: list[str]) -> tuple[bool, list[dict]]:
    cursor = 0
    witnesses = []
    for pattern in patterns:
        regex = re.compile(pattern)
        for index in range(cursor, len(ops)):
            if regex.search(ops[index]):
                witnesses.append({"pattern": pattern, "operation_index": index, "operation": ops[index]})
                cursor = index + 1
                break
        else:
            return False, witnesses
    return True, witnesses


def issuer_gating_witness(ops: list[str], needle: str) -> dict | None:
    """Locate either direct SASS predication or nearby predicated control flow.

    ptxas may lower a PTX guard to an ``@P``/``@UP`` prefix on the target
    instruction, or surround the target with a convergent conditional region.
    Both are observable issuer-gating mechanisms; requiring only the first one
    rejects valid O0 and CTA-group-1 lowering.
    """
    target_index = next((i for i, op in enumerate(ops) if needle in op), None)
    if target_index is None:
        return None
    target = ops[target_index]
    if target.startswith("@"):
        return {
            "target": needle,
            "mechanism": "instruction_predicate",
            "target_index": target_index,
            "operation": target,
        }
    window_start = max(0, target_index - 48)
    candidates = [
        (i, ops[i])
        for i in range(window_start, target_index)
        if ops[i].startswith("@") and "BRA" in ops[i]
    ]
    if candidates:
        index, operation = candidates[-1]
        return {
            "target": needle,
            "mechanism": "predicated_control_flow",
            "target_index": target_index,
            "operation_index": index,
            "operation": operation,
        }
    return None


def required_sequence(source: str) -> list[str]:
    if source.startswith("effect_"):
        sequence = [r"FENCE\.VIEW\.ASYNC\.S"]
        if "_st_wait_" in source:
            sequence.extend((r"\bSTTM", r"FENCE\.VIEW\.ASYNC\.T"))
        sequence.extend(
            (
                r"\bUTCHMMA(?:\.2CTA)?\b",
                r"\bUTCBAR(?:\.2CTA)?(?:\.MULTICAST)?\b",
                r"SYNCS\.PHASECHK",
                r"\bLDTM",
                r"\bSTG",
                r"UVIRTCOUNT\.DEALLOC\.SMPOOL",
            )
        )
        return sequence
    if source.startswith("ctx_proxy_fence_"):
        return [r"FENCE\.VIEW\.ASYNC\.S"]
    if source.startswith("ctx_commit_"):
        return [r"\bUTCBAR"]
    if source.startswith("ctx_alloc_"):
        return [r"UVIRTCOUNT\.DEALLOC\.SMPOOL"]
    if source.startswith("ctx_mbarrier_"):
        return [r"SYNCS\.EXCH", r"SYNCS\.PHASECHK", r"SYNCS\.CCTL\.IV"]
    if source == "ctx_ld_wait.ptx":
        return [r"\bLDTM", r"\bSTG"]
    if source == "ctx_st_wait.ptx":
        return [r"\bSTTM", r"FENCE\.VIEW\.ASYNC\.T"]
    return []


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
    sass_dir = work_dir / "sass"
    cubin_dir.mkdir(parents=True)
    sass_dir.mkdir(parents=True)
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
        if not result["artifact_valid"]:
            continue
        disassembly = subprocess.run(
            [str(args.nvdisasm), str(cubin_dir / result["output"])],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        sass_path = sass_dir / f"{Path(result['output']).stem}.sass"
        sass_path.write_text(disassembly, encoding="utf-8")
        ops = operations(disassembly)
        required = required_sequence(result["source"])
        ordered, witnesses = ordered_match(ops, required)
        semantic_failures = []
        issuer_gating = []
        if result["source"].startswith("effect_cg2_"):
            if not any("SR_CgaCtaId" in op for op in ops):
                semantic_failures.append("missing CTA-rank issuer selection")
            if not any("UTCHMMA.2CTA" in op for op in ops):
                semantic_failures.append("missing group-2 MMA")
            if not any("UTCBAR.2CTA.MULTICAST" in op for op in ops):
                semantic_failures.append("missing group-2 multicast completion")
        if result["source"].startswith("effect_cg1_"):
            if any("UTCHMMA.2CTA" in op or "UTCBAR.2CTA" in op for op in ops):
                semantic_failures.append("unexpected group-2 operation in group-1 slice")
        if result["source"].startswith("effect_"):
            issuer_gating = [
                witness
                for needle in ("UTCHMMA", "UTCBAR")
                if (witness := issuer_gating_witness(ops, needle)) is not None
            ]
            if len(issuer_gating) != 2:
                semantic_failures.append(
                    "MMA/commit issuer gating is neither directly predicated nor "
                    "guarded by nearby predicated control flow"
                )
        sass_checks.append(
            {
                "source": result["source"],
                "layer": result["layer"],
                "optimization": result["optimization"],
                "sass_file": str(sass_path.relative_to(work_dir)),
                "sass_sha256": hashlib.sha256(disassembly.encode()).hexdigest(),
                "instruction_count": len(ops),
                "required_ordered_patterns": required,
                "ordered_witnesses": witnesses,
                "issuer_gating_witnesses": issuer_gating,
                "semantic_failures": semantic_failures,
                "status": "PASS" if ordered and not semantic_failures else "FAIL",
            }
        )
    sass_failures = [item for item in sass_checks if item["status"] != "PASS"]
    expected_sass_checks = (
        generation["case_count"] * len(OPTIMIZATIONS)
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
    nvdisasm_version = subprocess.run(
        [str(args.nvdisasm), "--version"],
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
        "nvdisasm_sha256": hashlib.sha256(args.nvdisasm.read_bytes()).hexdigest(),
        "nvdisasm_version": nvdisasm_version,
        "compile_attempt_count": len(results),
        "compile_pass_count": len(results) - len(compile_failures),
        "compile_failure_count": len(compile_failures),
        "source_validation": source_validation,
        "sass_directory": str(sass_dir.relative_to(work_dir)),
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

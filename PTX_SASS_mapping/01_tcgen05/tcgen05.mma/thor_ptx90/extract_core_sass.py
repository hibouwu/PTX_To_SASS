#!/usr/bin/env python3
"""Extract core tcgen05.mma SASS and attribute it to generated PTX cases."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import subprocess

from suite_utils import reset_owned_directory


ROOT = Path(__file__).resolve().parent
OPTIMIZATIONS = ("O0", "O1", "O2", "O3")
SECTION_RE = re.compile(
    r'^\s*\.section\s+\.text\.([^,"]+),"ax",@progbits\s*$',
    re.MULTILINE,
)
INSTRUCTION_RE = re.compile(
    r"/\*([0-9a-fA-F]+)\*/\s+(.*?)\s*;\s*"
    r"/\*\s*(0x[0-9a-fA-F]+)\s*\*/\s*\n\s*"
    r"/\*\s*(0x[0-9a-fA-F]+)\s*\*/"
)
TARGET_MNEMONIC_RE = re.compile(r"\b(UTC[A-Z0-9]*MMA(?:\.[A-Z0-9]+)*)\b")


def load_manifest(source_dir: Path) -> list[dict]:
    manifest_path = source_dir / "manifest.jsonl"
    rows = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError(f"empty manifest: {manifest_path}")
    return rows


def split_text_sections(disassembly: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(disassembly))
    return {
        match.group(1): disassembly[
            match.start() : (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(disassembly)
            )
        ]
        for index, match in enumerate(matches)
    }


def target_instructions(section: str) -> list[dict]:
    targets = []
    for match in INSTRUCTION_RE.finditer(section):
        operation = match.group(2).strip()
        mnemonic_match = TARGET_MNEMONIC_RE.search(operation)
        if mnemonic_match is None:
            continue
        targets.append(
            {
                "offset": f"0x{match.group(1).lower()}",
                "mnemonic": mnemonic_match.group(1),
                "operation": operation,
                "encoding_words": [
                    match.group(3).lower(),
                    match.group(4).lower(),
                ],
            }
        )
    return targets


def disassemble_one(
    nvdisasm: Path,
    cubin: Path,
    sass_output: Path,
) -> dict:
    command = [
        str(nvdisasm),
        "--print-code",
        "--separate-functions",
        "--print-instruction-encoding",
        str(cubin),
    ]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode == 0:
        sass_output.write_text(completed.stdout, encoding="utf-8")
    output_exists = sass_output.is_file()
    output_size = sass_output.stat().st_size if output_exists else 0
    return {
        "cubin": cubin.name,
        "sass_file": str(sass_output),
        "command": command,
        "returncode": completed.returncode,
        "stderr": completed.stderr,
        "output_exists": output_exists,
        "output_size": output_size,
        "output_sha256": (
            hashlib.sha256(sass_output.read_bytes()).hexdigest()
            if output_exists
            else None
        ),
        "artifact_valid": completed.returncode == 0 and output_size > 0,
    }


def extract_suite(
    *,
    source_dir: Path,
    cubin_dir: Path,
    output_dir: Path,
    nvdisasm: Path,
    optimizations: tuple[str, ...] | list[str],
    jobs: int,
) -> dict:
    if jobs < 1:
        raise ValueError("jobs must be positive")
    output_dir = reset_owned_directory(
        output_dir, owner="thor_tcgen05_mma_sass", protected=(ROOT,)
    )
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True)

    manifest_rows = load_manifest(source_dir)
    rows_by_shard: dict[str, list[dict]] = {}
    for row in manifest_rows:
        rows_by_shard.setdefault(row["source_shard"], []).append(row)

    tasks = []
    missing_cubins = []
    for source_shard in sorted(rows_by_shard):
        stem = Path(source_shard).stem
        for optimization in optimizations:
            cubin = cubin_dir / f"{stem}_{optimization}.cubin"
            sass_output = raw_dir / f"{stem}_{optimization}.sass"
            if cubin.is_file():
                tasks.append((source_shard, optimization, cubin, sass_output))
            else:
                missing_cubins.append(
                    {
                        "source_shard": source_shard,
                        "optimization": optimization,
                        "expected_cubin": str(cubin),
                    }
                )

    disassembly_results = []
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        pending = {
            executor.submit(disassemble_one, nvdisasm, cubin, sass_output): (
                source_shard,
                optimization,
            )
            for source_shard, optimization, cubin, sass_output in tasks
        }
        for future in as_completed(pending):
            source_shard, optimization = pending[future]
            result = future.result()
            result["source_shard"] = source_shard
            result["optimization"] = optimization
            disassembly_results.append(result)
            status = "PASS" if result["artifact_valid"] else "FAIL"
            print(f"{status} SASS {source_shard} {optimization}")

    disassembly_results.sort(
        key=lambda item: (item["source_shard"], item["optimization"])
    )
    attribution_rows = []
    for result in disassembly_results:
        if not result["artifact_valid"]:
            continue
        sections = split_text_sections(
            Path(result["sass_file"]).read_text(encoding="utf-8")
        )
        result["text_section_count"] = len(sections)
        for manifest_row in rows_by_shard[result["source_shard"]]:
            kernel = manifest_row["kernel"]
            section = sections.get(kernel)
            sass_targets = target_instructions(section) if section is not None else []
            expected_count = manifest_row["target_occurrence_count"]
            if section is None:
                status = "MISSING_KERNEL"
            elif len(sass_targets) != expected_count:
                status = "TARGET_COUNT_MISMATCH"
            else:
                status = "COMPLETE"
            occurrence_attribution = []
            for occurrence_index in range(max(expected_count, len(sass_targets))):
                occurrence_attribution.append(
                    {
                        "occurrence_index": occurrence_index,
                        "ptx_instruction": (
                            manifest_row["target_instructions"][occurrence_index]
                            if occurrence_index < expected_count
                            else None
                        ),
                        "sass_target": (
                            sass_targets[occurrence_index]
                            if occurrence_index < len(sass_targets)
                            else None
                        ),
                    }
                )
            attribution_rows.append(
                {
                    "case_label": manifest_row["case_label"],
                    "source_implementation_id": manifest_row[
                        "source_implementation_id"
                    ],
                    "source_shard": result["source_shard"],
                    "optimization": result["optimization"],
                    "kernel": kernel,
                    "cubin": result["cubin"],
                    "sass_file": result["sass_file"],
                    "attribution_method": "KERNEL_SECTION_AND_SOURCE_ORDER",
                    "expected_ptx_occurrence_count": expected_count,
                    "observed_sass_target_count": len(sass_targets),
                    "status": status,
                    "occurrences": occurrence_attribution,
                }
            )

    attribution_rows.sort(
        key=lambda item: (
            item["source_shard"],
            item["optimization"],
            item["case_label"],
        )
    )
    attribution_path = output_dir / "sass_attribution.jsonl"
    with attribution_path.open("w", encoding="utf-8") as handle:
        for row in attribution_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    disassembly_failures = [
        item for item in disassembly_results if not item["artifact_valid"]
    ]
    attribution_failures = [
        item for item in attribution_rows if item["status"] != "COMPLETE"
    ]
    expected_case_attributions = len(manifest_rows) * len(optimizations)
    expected_target_occurrences = (
        sum(row["target_occurrence_count"] for row in manifest_rows)
        * len(optimizations)
    )
    observed_target_occurrences = sum(
        row["observed_sass_target_count"] for row in attribution_rows
    )
    status = (
        "COMPLETE"
        if not missing_cubins
        and not disassembly_failures
        and not attribution_failures
        and len(attribution_rows) == expected_case_attributions
        and observed_target_occurrences == expected_target_occurrences
        else "FAILED"
    )
    nvdisasm_version = subprocess.run(
        [str(nvdisasm), "--version"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip().splitlines()
    summary = {
        "schema_version": "thor_tcgen05_mma_sass_attribution_v1",
        "status": status,
        "attribution_scope": "CORE_MMA_MNEMONIC",
        "attribution_method": "KERNEL_SECTION_AND_SOURCE_ORDER",
        "nvdisasm_path": str(nvdisasm),
        "nvdisasm_sha256": hashlib.sha256(nvdisasm.read_bytes()).hexdigest(),
        "nvdisasm_version": nvdisasm_version,
        "optimization_levels": list(optimizations),
        "expected_disassembly_count": len(rows_by_shard) * len(optimizations),
        "disassembly_count": len(disassembly_results),
        "disassembly_pass_count": len(disassembly_results)
        - len(disassembly_failures),
        "expected_case_attribution_count": expected_case_attributions,
        "case_attribution_count": len(attribution_rows),
        "complete_case_attribution_count": len(attribution_rows)
        - len(attribution_failures),
        "expected_ptx_target_occurrence_count": expected_target_occurrences,
        "observed_sass_target_count": observed_target_occurrences,
        "missing_cubin_count": len(missing_cubins),
        "disassembly_failure_count": len(disassembly_failures),
        "attribution_failure_count": len(attribution_failures),
        "raw_sass_directory": str(raw_dir),
        "attribution_file": str(attribution_path),
    }
    report = {
        **summary,
        "missing_cubins": missing_cubins,
        "disassembly_failures": disassembly_failures,
        "attribution_failures": attribution_failures,
        "disassemblies": disassembly_results,
    }
    (output_dir / "sass_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--cubin-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--optimizations",
        nargs="+",
        choices=OPTIMIZATIONS,
        default=OPTIMIZATIONS,
    )
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--nvdisasm", type=Path, default=Path("/usr/local/cuda/bin/nvdisasm")
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = extract_suite(
        source_dir=args.source_dir,
        cubin_dir=args.cubin_dir,
        output_dir=args.output_dir,
        nvdisasm=args.nvdisasm,
        optimizations=args.optimizations,
        jobs=args.jobs,
    )
    print(
        f"{summary['complete_case_attribution_count']}/"
        f"{summary['expected_case_attribution_count']} case attributions complete; "
        f"{summary['attribution_file']}"
    )
    if summary["status"] != "COMPLETE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

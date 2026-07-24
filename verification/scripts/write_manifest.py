#!/usr/bin/env python3
"""Validate and record the complete B200 PTX-to-SASS acquisition set."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent
PTX_DIR = BASE_DIR / "ptx_sources"
CUBIN_DIR = BASE_DIR / "cubins"
SASS_DIR = BASE_DIR / "sass_dumps"
SASS_PTX_DIR = BASE_DIR / "sass_ptx_dumps"
RESULTS_DIR = BASE_DIR / "results"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict:
    return {
        "path": str(path.relative_to(BASE_DIR)),
        "size": path.stat().st_size,
        "sha256": sha256(path),
    }


def command_output(args: list[str]) -> str:
    try:
        result = subprocess.run(
            args,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError:
        return "NOT_FOUND"
    return result.stdout.strip()


def git_metadata() -> dict:
    commit = command_output(["git", "-C", str(REPO_DIR), "rev-parse", "HEAD"])
    status = command_output(
        ["git", "-C", str(REPO_DIR), "status", "--porcelain"]
    )
    return {
        "commit": commit,
        "dirty": bool(status),
        "status_entry_count": len(status.splitlines()) if status else 0,
    }


def expected_artifact_names(ptx_files: list[Path]) -> tuple[set[str], list[Path]]:
    expected = set()
    unsupported = []
    for path in ptx_files:
        if "EXPECTED_UNSUPPORTED_BY_PTX_ISA:" in path.read_text(encoding="utf-8"):
            unsupported.append(path)
            continue
        stem = f"{path.parent.name}__{path.stem}"
        expected.update({f"{stem}_O0", f"{stem}_O3"})
    return expected, unsupported


def require_exact_set(directory: Path, suffix: str, expected: set[str]) -> list[Path]:
    files = sorted(directory.glob(f"*{suffix}"))
    actual = {path.name.removesuffix(suffix) for path in files}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise RuntimeError(
            f"Artifact set mismatch in {directory}: missing={missing[:10]}, extra={extra[:10]}"
        )
    errors = sorted(path for path in directory.glob("*.err") if path.stat().st_size)
    if errors:
        raise RuntimeError(f"Non-empty error logs in {directory}: {errors[:10]}")
    return files


def validate_sass(files: list[Path], label: str) -> int:
    instruction_count = 0
    for path in files:
        parsed = analyze.parse_sass_file(path, label)
        if parsed is None:
            raise RuntimeError(f"Failed to parse {path}")
        instruction_count += len(parsed.all_instructions)
    return instruction_count


def instruction_sequence(path: Path, label: str) -> list[tuple[str, str, str]]:
    parsed = analyze.parse_sass_file(path, label)
    if parsed is None:
        raise RuntimeError(f"Failed to parse {path}")
    return [
        (instr["predicate"].strip(), instr["opcode"], instr["operands"].strip())
        for instr in parsed.all_instructions
    ]


def require_matching_disassembly(
    sass_g: list[Path], sass_gp: list[Path]
) -> None:
    gp_by_stem = {path.stem: path for path in sass_gp}
    for g_path in sass_g:
        gp_path = gp_by_stem[g_path.stem]
        g_sequence = instruction_sequence(g_path, "-g")
        gp_sequence = instruction_sequence(gp_path, "-gp")
        if g_sequence != gp_sequence:
            raise RuntimeError(
                f"-g/-gp instruction sequence mismatch for {g_path.stem}: "
                f"{len(g_sequence)} != {len(gp_sequence)} or content differs"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", default="sm_100a")
    parser.add_argument(
        "--output", type=Path, default=RESULTS_DIR / "artifact_manifest.json"
    )
    args = parser.parse_args()

    ptx_files = sorted(PTX_DIR.rglob("*.ptx"))
    if not ptx_files:
        raise RuntimeError("No PTX inputs found")
    targets = {
        line.split(None, 1)[1]
        for path in ptx_files
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(".target ")
    }
    if targets != {args.arch}:
        raise RuntimeError(f"PTX targets {sorted(targets)} do not equal --arch {args.arch}")

    expected, unsupported = expected_artifact_names(ptx_files)
    cubins = require_exact_set(CUBIN_DIR, ".cubin", expected)
    sass_g = require_exact_set(SASS_DIR, ".sass", expected)
    sass_gp = require_exact_set(SASS_PTX_DIR, ".sass", expected)
    g_instruction_count = validate_sass(sass_g, "O0/O3 -g")
    gp_instruction_count = validate_sass(sass_gp, "O0/O3 -gp")
    require_matching_disassembly(sass_g, sass_gp)

    by_name = {
        "cubin": {path.stem: path for path in cubins},
        "sass_g": {path.stem: path for path in sass_g},
        "sass_gp": {path.stem: path for path in sass_gp},
    }
    cases = []
    for ptx_path in ptx_files:
        case_stem = f"{ptx_path.parent.name}__{ptx_path.stem}"
        item = {
            "case": case_stem,
            "ptx": file_record(ptx_path),
            "unsupported_by_ptx_isa": ptx_path in unsupported,
            "artifacts": {},
        }
        if ptx_path not in unsupported:
            for opt in ("O0", "O3"):
                artifact_stem = f"{case_stem}_{opt}"
                item["artifacts"][opt] = {
                    kind: file_record(paths[artifact_stem])
                    for kind, paths in by_name.items()
                }
        cases.append(item)

    report_path = RESULTS_DIR / "mapping_report.csv"
    if not report_path.exists():
        raise RuntimeError(f"Missing analysis report: {report_path}")

    manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "architecture": args.arch,
        "ptx_isa_versions": sorted(
            {
                line.split(None, 1)[1]
                for path in ptx_files
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith(".version ")
            }
        ),
        "environment": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": sys.version,
            "ptxas_path": shutil.which("ptxas"),
            "ptxas_version": command_output(["ptxas", "--version"]),
            "nvdisasm_path": shutil.which("nvdisasm"),
            "nvdisasm_version": command_output(["nvdisasm", "--version"]),
            "gpu": command_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,uuid,driver_version",
                    "--format=csv,noheader",
                ]
            ),
            "git": git_metadata(),
        },
        "commands": {
            "compile_O0": f"ptxas -arch={args.arch} -O0 -lineinfo -o <cubin> <ptx>",
            "compile_O3": f"ptxas -arch={args.arch} -O3 -lineinfo -o <cubin> <ptx>",
            "disassemble_source": "nvdisasm -g <cubin>",
            "disassemble_ptx": "nvdisasm -gp <cubin>",
        },
        "summary": {
            "ptx_files": len(ptx_files),
            "legal_ptx_files": len(ptx_files) - len(unsupported),
            "unsupported_ptx_files": len(unsupported),
            "cubins": len(cubins),
            "sass_g_files": len(sass_g),
            "sass_gp_files": len(sass_gp),
            "sass_g_instruction_lines_parsed": g_instruction_count,
            "sass_gp_instruction_lines_parsed": gp_instruction_count,
            "unparsed_instruction_lines": 0,
            "g_gp_instruction_sequences_equal": True,
        },
        "pipeline_scripts": {
            path.name: file_record(path)
            for path in sorted((BASE_DIR / "scripts").glob("*"))
            if path.is_file() and path.suffix in {".py", ".sh"}
        },
        "analysis_report": file_record(report_path),
        "cases": cases,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(args.output)
    print(f"Manifest written to: {args.output}")
    print(json.dumps(manifest["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

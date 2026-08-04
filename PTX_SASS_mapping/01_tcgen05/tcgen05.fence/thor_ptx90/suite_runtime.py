#!/usr/bin/env python3
"""Self-contained Thor experiment runtime for tcgen05.fence.

This local copy serves only tcgen05.fence; it deliberately has no dependency on
another tcgen05 instruction suite. Runtime semantics are outside pass criteria.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Callable, Iterable


PTX_VERSION = "9.0"
PTX_TARGET = "sm_110a"
OPTIMIZATIONS = ("O0", "O1", "O2", "O3")
OWNER_MARKER = ".tcgen05-suite-owner.json"
INSTRUCTION_RE = re.compile(
    r"/\*([0-9a-fA-F]+)\*/\s+(.*?)\s*;\s*"
    r"/\*\s*(0x[0-9a-fA-F]+)\s*\*/\s*\n\s*"
    r"/\*\s*(0x[0-9a-fA-F]+)\s*\*/"
)


@dataclass(frozen=True)
class Case:
    label: str
    coordinates: dict
    declarations: tuple[str, ...] = ()
    parameters: tuple[str, ...] = ()
    registers: tuple[str, ...] = ()
    preparation: tuple[str, ...] = ()
    target: tuple[str, ...] = ()
    observation: tuple[str, ...] = ()
    directives: tuple[str, ...] = ()
    expected: str = "accept"
    reason: str = ""


@dataclass(frozen=True)
class Spec:
    opcode: str
    target_patterns: tuple[str, ...]
    factors: tuple[dict, ...]
    syntax_cases: Callable[[], list[Case]]
    expanded_cases: Callable[[], list[Case]]
    negative_cases: Callable[[], list[Case]]
    empty_target_allowed: Callable[[dict], bool] = lambda _coordinates: False


def stable_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def reset_owned_directory(path: Path, owner: str, protected: Iterable[Path] = ()) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == Path(resolved.anchor) or len(resolved.parts) < 3:
        raise SystemExit(f"refusing unsafe output directory: {resolved}")
    protected_paths = (Path.cwd().resolve(), *(item.resolve() for item in protected))
    for item in protected_paths:
        if resolved == item or resolved in item.parents:
            raise SystemExit(f"refusing protected directory or ancestor: {resolved}")
    marker = resolved / OWNER_MARKER
    if resolved.exists():
        if not marker.is_file():
            raise SystemExit(f"refusing unowned directory without {OWNER_MARKER}: {resolved}")
        data = json.loads(marker.read_text(encoding="utf-8"))
        if data.get("owner") != owner:
            raise SystemExit(f"owner mismatch for {resolved}")
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)
    marker.write_text(
        json.dumps({"schema_version": "tcgen05_suite_owner_v1", "owner": owner}) + "\n",
        encoding="utf-8",
    )
    return resolved


def _params(items: tuple[str, ...]) -> list[str]:
    return [f"    {item}{',' if index + 1 < len(items) else ''}" for index, item in enumerate(items)]


def module_source(case: Case, opcode: str) -> str:
    lines = [
        f".version {PTX_VERSION}",
        f".target {PTX_TARGET}",
        ".address_size 64",
        f'.file 1 "{case.label}.ptx"',
        "",
        *case.declarations,
        "",
        f"// OPCODE tcgen05.{opcode}",
        "// COORDINATES " + json.dumps(case.coordinates, sort_keys=True, separators=(",", ":")),
        f".visible .entry {case.label}(",
        *_params(case.parameters),
        ")",
        *[f"    {item}" for item in case.directives],
        "{",
        *[f"    {item}" for item in case.registers],
        "    // PREPARATION_BEGIN",
        *[f"    {item}" for item in case.preparation],
        "    // PREPARATION_END",
        "    // TARGET_PATTERN_BEGIN",
        *[f"    {item}" for item in case.target],
        "    // TARGET_PATTERN_END",
        "    // OBSERVATION_BEGIN",
        *[f"    {item}" for item in case.observation],
        "    // OBSERVATION_END",
        "    ret;",
        "}",
        "",
    ]
    return "\n".join(lines)


def _case_id(opcode: str, index: int, coords: dict) -> str:
    short = opcode.replace("_", "")
    return f"thor_tcgen05_{short}_{index:04d}_{stable_hash(coords)[:8]}"


def materialize_cases(spec: Spec, mode: str) -> list[Case]:
    raw = spec.syntax_cases() if mode == "syntax" else spec.expanded_cases()
    return [Case(_case_id(spec.opcode, index, case.coordinates), case.coordinates, case.declarations, case.parameters, case.registers, case.preparation, case.target, case.observation, case.directives, case.expected, case.reason) for index, case in enumerate(raw, 1)]


def generate(spec: Spec, mode: str, output: Path, suite_root: Path) -> dict:
    output = reset_owned_directory(output, f"thor_tcgen05_{spec.opcode}_generated", (suite_root,))
    rows = []
    for case in materialize_cases(spec, mode):
        source = module_source(case, spec.opcode)
        path = output / f"{case.label}.ptx"
        path.write_text(source, encoding="utf-8")
        rows.append({"schema_version": "tcgen05_static_manifest_v1", "case_id": case.label, "case_label": case.label, "kernel": case.label, "opcode": f"tcgen05.{spec.opcode}", "mode": mode, "coordinates": case.coordinates, "semantic_form": case.coordinates, "semantic_form_id": stable_hash(case.coordinates), "source_variant": {"mode": mode}, "source_variant_id": stable_hash({"mode": mode}), "source_implementation_id": stable_hash({"case": case.label, "source": source}), "target_instructions": list(case.target), "target_occurrence_count": len(case.target), "validation_scope": "STATIC_ATTRIBUTION", "environment_id": "thor_cuda13_ptx90_sm110a", "source_file": path.name, "source_sha256": hashlib.sha256(source.encode()).hexdigest(), "expected": case.expected})
    (output / "manifest.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    summary = {"schema_version": "tcgen05_generation_summary_v1", "opcode": f"tcgen05.{spec.opcode}", "mode": mode, "case_count": len(rows), "manifest_sha256": stable_hash(rows)}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validate_sources(spec, output)
    return summary


def validate_sources(spec: Spec, source_dir: Path) -> dict:
    rows = [json.loads(line) for line in (source_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    errors = []
    seen = set()
    for row in rows:
        if row["case_id"] in seen: errors.append(f"duplicate case_id {row['case_id']}")
        seen.add(row["case_id"])
        path = source_dir / row["source_file"]
        if not path.is_file(): errors.append(f"missing {path.name}"); continue
        text = path.read_text(encoding="utf-8")
        if hashlib.sha256(text.encode()).hexdigest() != row["source_sha256"]: errors.append(f"hash mismatch {path.name}")
        if text.count("// TARGET_PATTERN_BEGIN") != 1 or text.count("// TARGET_PATTERN_END") != 1: errors.append(f"target markers {path.name}")
        if f"tcgen05.{spec.opcode}" not in text: errors.append(f"opcode marker missing {path.name}")
    if errors: raise ValueError("; ".join(errors))
    return {"status": "PASS", "case_count": len(rows), "error_count": 0}


def _tool_identity(path: Path) -> dict:
    completed = subprocess.run([str(path), "--version"], text=True, capture_output=True, check=True)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "version": completed.stdout.strip().splitlines()}


def _compile_one(ptxas: Path, source: Path, cubin: Path, opt: str) -> dict:
    command = [str(ptxas), f"-arch={PTX_TARGET}", f"-{opt}", str(source), "-o", str(cubin)]
    started = time.monotonic()
    done = subprocess.run(command, text=True, capture_output=True)
    valid = done.returncode == 0 and cubin.is_file() and cubin.stat().st_size > 0
    return {"source": source.name, "optimization": opt, "command": command, "returncode": done.returncode, "seconds": round(time.monotonic() - started, 4), "stdout": done.stdout, "stderr": done.stderr, "artifact_valid": valid, "output": cubin.name}


def _disassemble_one(nvdisasm: Path, cubin: Path, output: Path) -> dict:
    command = [str(nvdisasm), "--print-code", "--separate-functions", "--print-instruction-encoding", str(cubin)]
    done = subprocess.run(command, text=True, capture_output=True)
    if done.returncode == 0: output.write_text(done.stdout, encoding="utf-8")
    return {"returncode": done.returncode, "stderr": done.stderr, "artifact_valid": done.returncode == 0 and output.is_file() and output.stat().st_size > 0}


def parse_instructions(text: str) -> list[dict]:
    return [{"offset": f"0x{m.group(1).lower()}", "operation": m.group(2).strip(), "encoding_words": [m.group(3).lower(), m.group(4).lower()]} for m in INSTRUCTION_RE.finditer(text)]


def compile_suite(spec: Spec, suite_root: Path, mode: str, work_dir: Path, ptxas: Path, nvdisasm: Path, jobs: int, optimizations: tuple[str, ...], summary_output: Path | None) -> dict:
    work_dir = reset_owned_directory(work_dir, f"thor_tcgen05_{spec.opcode}_check", (suite_root,))
    sources = work_dir / "sources"; cubins = work_dir / "cubins"; sass = work_dir / "sass"
    cubins.mkdir(); sass.mkdir()
    generation = generate(spec, mode, sources, suite_root)
    source_files = sorted(sources.glob("*.ptx"))
    tasks = [(src, cubins / f"{src.stem}_{opt}.cubin", opt) for src in source_files for opt in optimizations]
    results = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(_compile_one, ptxas, src, out, opt): (src, opt) for src, out, opt in tasks}
        for future in as_completed(futures):
            result = future.result(); results.append(result)
            print(f"{'PASS' if result['artifact_valid'] else 'FAIL'} {result['source']} {result['optimization']}")
    results.sort(key=lambda row: (row["source"], row["optimization"]))
    compile_failures = [row for row in results if not row["artifact_valid"]]
    manifest = {row["case_id"]: row for row in (json.loads(line) for line in (sources / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
    attributions = []
    disassembly_failures = []
    if not compile_failures:
        for result in results:
            case_id = Path(result["source"]).stem
            cubin = cubins / result["output"]
            sass_path = sass / f"{case_id}_{result['optimization']}.sass"
            status = _disassemble_one(nvdisasm, cubin, sass_path)
            if not status["artifact_valid"]: disassembly_failures.append({"cubin": cubin.name, **status}); continue
            instructions = parse_instructions(sass_path.read_text(encoding="utf-8"))
            targets = [item for item in instructions if any(pattern in item["operation"] for pattern in spec.target_patterns)]
            attributions.append({"schema_version": "tcgen05_static_attribution_v1", "case_id": case_id, "case_label": case_id, "occurrence_index": 0, "ptx_instruction": "\n".join(manifest[case_id]["target_instructions"]), "status": "ATTRIBUTED" if targets else "TARGET_ELIMINATED", "observation_level": "exact", "sass_instructions": [item["operation"] for item in targets], "encoding_words": [word for item in targets for word in item["encoding_words"]], "environment_id": "thor_cuda13_ptx90_sm110a", "opcode": f"tcgen05.{spec.opcode}", "optimization": result["optimization"], "coordinates": manifest[case_id]["coordinates"], "instruction_count": len(instructions), "target_patterns": list(spec.target_patterns), "target_instructions": targets, "full_instructions": instructions, "sass_file": sass_path.name})
    (sass / "sass_attribution.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in attributions), encoding="utf-8")
    missing_target = [row for row in attributions if not row["target_instructions"] and not spec.empty_target_allowed(row["coordinates"])]
    status = "PASS" if not compile_failures and not disassembly_failures and not missing_target else "FAIL"
    report = {"schema_version": "tcgen05_static_compile_report_v1", "validation_status": status, "opcode": f"tcgen05.{spec.opcode}", "mode": mode, "generation": generation, "optimizations": list(optimizations), "ptxas": _tool_identity(ptxas), "nvdisasm": _tool_identity(nvdisasm), "compile_attempt_count": len(results), "compile_failure_count": len(compile_failures), "disassembly_failure_count": len(disassembly_failures), "attribution_count": len(attributions), "missing_target_count": len(missing_target), "compile_results": results, "disassembly_failures": disassembly_failures, "missing_targets": [{"case_id": row["case_id"], "optimization": row["optimization"]} for row in missing_target]}
    (work_dir / "compile_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if summary_output:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        compact = {key: value for key, value in report.items() if key not in {"compile_results", "disassembly_failures", "missing_targets"}}
        summary_output.write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if status != "PASS": raise SystemExit(1)
    return report


def check_negative(spec: Spec, suite_root: Path, work_dir: Path, ptxas: Path, summary_output: Path | None) -> dict:
    work_dir = reset_owned_directory(work_dir, f"thor_tcgen05_{spec.opcode}_negative", (suite_root,))
    results = []
    for index, raw in enumerate(spec.negative_cases(), 1):
        case = Case(_case_id(spec.opcode + "_negative", index, raw.coordinates), raw.coordinates, raw.declarations, raw.parameters, raw.registers, raw.preparation, raw.target, raw.observation, raw.directives, raw.expected, raw.reason)
        source = work_dir / f"{case.label}.ptx"; cubin = work_dir / f"{case.label}.cubin"
        source.write_text(module_source(case, spec.opcode), encoding="utf-8")
        result = _compile_one(ptxas, source, cubin, "O0")
        passed = result["returncode"] != 0
        results.append({"case_id": case.label, "coordinates": case.coordinates, "reason": case.reason, "expected": "reject", "observed_returncode": result["returncode"], "stderr": result["stderr"], "status": "PASS" if passed else "FAIL"})
    failures = [row for row in results if row["status"] != "PASS"]
    report = {"schema_version": "tcgen05_negative_probe_report_v1", "validation_status": "PASS" if not failures else "FAIL", "opcode": f"tcgen05.{spec.opcode}", "probe_count": len(results), "expected_rejection_pass_count": len(results) - len(failures), "results": results}
    (work_dir / "negative_probe_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if summary_output:
        summary_output.parent.mkdir(parents=True, exist_ok=True); summary_output.write_text(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if failures: raise SystemExit(1)
    return report


def analyze(spec: Spec, manifest_path: Path, attribution_path: Path, output_dir: Path, suite_root: Path) -> dict:
    output_dir = reset_owned_directory(output_dir, f"thor_tcgen05_{spec.opcode}_analysis", (suite_root,))
    manifest = {row["case_id"]: row for row in (json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip())}
    rows = [json.loads(line) for line in attribution_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    forward = []
    inverse_groups: dict[str, list[dict]] = {}
    for row in rows:
        signature = tuple(item["operation"] for item in row["target_instructions"])
        encoding = tuple(tuple(item["encoding_words"]) for item in row["target_instructions"])
        rule = {"case_id": row["case_id"], "optimization": row["optimization"], "coordinates": manifest[row["case_id"]]["coordinates"], "target_signature": list(signature), "target_encoding": [list(item) for item in encoding]}
        forward.append(rule)
        key = stable_hash({"signature": signature, "encoding": encoding})
        inverse_groups.setdefault(key, []).append(rule)
    inverse = [{"signature_id": key, "target_signature": group[0]["target_signature"], "target_encoding": group[0]["target_encoding"], "candidate_count": len(group), "candidates": [{"case_id": item["case_id"], "optimization": item["optimization"], "coordinates": item["coordinates"]} for item in group]} for key, group in sorted(inverse_groups.items())]
    rules = []
    safe_opcode = spec.opcode.replace("_", "-")
    for index, item in enumerate(forward, 1):
        rules.append({"rule_id": f"tcgen05.{safe_opcode}.forward.{index:06d}", "direction": "PTX_TO_SASS", "level": "encoding", "when": {"coordinates": item["coordinates"], "optimization": item["optimization"]}, "then": {"target_signature": item["target_signature"], "target_encoding": item["target_encoding"]}, "evidence_grade": "OBSERVATION", "evidence": {"support_count": 1, "counterexample_count": 0, "case_labels": [item["case_id"]]}, "limitations": ["static compilation and disassembly only"]})
    for index, item in enumerate(inverse, 1):
        rules.append({"rule_id": f"tcgen05.{safe_opcode}.inverse.{index:06d}", "direction": "SASS_TO_PTX", "level": "encoding", "when": {"target_signature": item["target_signature"], "target_encoding": item["target_encoding"]}, "then": {"candidates": item["candidates"]}, "evidence_grade": "CONDITIONAL" if item["candidate_count"] > 1 else "OBSERVATION", "evidence": {"support_count": item["candidate_count"], "counterexample_count": 0, "case_labels": sorted({candidate["case_id"] for candidate in item["candidates"]})}, "limitations": ["inverse result is a candidate set when signatures collide"]})
    analysis = {"schema_version": "tcgen05_static_mapping_rules_v1", "environment": {"environment_id": "thor_cuda13_ptx90_sm110a", "ptx_version": PTX_VERSION, "target": PTX_TARGET}, "rules": rules, "opcode": f"tcgen05.{spec.opcode}", "forward_rule_count": len(forward), "inverse_signature_count": len(inverse), "forward_rules": forward, "inverse_rules": inverse, "scope": "static compilation and disassembly; no runtime semantic claim"}
    (output_dir / "mapping_rules.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = [f"# `tcgen05.{spec.opcode}` 自动规则候选", "", "本报告由 expanded manifest 与 O0–O3 反汇编归属机械生成，只记录静态指令选择证据，不声明运行时语义。", "", f"- 正向记录：{len(forward)}", f"- 唯一逆向签名：{len(inverse)}", "", "完整集合见 [`mapping_rules.json`](mapping_rules.json)。", ""]
    (output_dir / "mapping_rules.md").write_text("\n".join(md), encoding="utf-8")
    return analysis


def write_factors(spec: Spec, suite_root: Path) -> None:
    factors = []
    for factor in spec.factors:
        item = dict(factor)
        item["class"] = item["id"].split(".", 1)[0]
        item.setdefault("description", f"Controlled factor {item['id']} for tcgen05.{spec.opcode}.")
        item.setdefault("applicability", "See generated case coordinates and PTX grammar constraints.")
        factors.append(item)
    data = {"schema_version": "ptx_sass_factors_v1", "family_id": f"tcgen05.{spec.opcode}.thor_ptx90", "opcode": f"tcgen05.{spec.opcode}", "environment_id": "thor_cuda13_ptx90_sm110a", "factors": factors, "constraints": [], "coverage": {"strategy": "mixed", "strength": 2, "optimizations": list(OPTIMIZATIONS), "high_risk_interactions": [], "stopping_condition": "all generated legal cases compile and have target attribution at O0-O3; all registered negative probes reject"}, "semantic_scope": "STATIC_ONLY"}
    (suite_root / "factors.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _local_spec() -> Spec:
    from suite_spec import SPEC
    return SPEC


def cli_generate(suite_root: Path) -> None:
    spec = _local_spec()
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("syntax", "expanded"), default="syntax")
    parser.add_argument("--output", type=Path, default=suite_root / "generated")
    args = parser.parse_args()
    write_factors(spec, suite_root)
    print(json.dumps(generate(spec, args.mode, args.output, suite_root), indent=2))


def cli_validate(suite_root: Path) -> None:
    spec = _local_spec()
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", nargs="?", type=Path, default=suite_root / "generated")
    args = parser.parse_args()
    print(json.dumps(validate_sources(spec, args.source_dir), indent=2))


def cli_check(suite_root: Path) -> None:
    spec = _local_spec()
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("syntax", "expanded"), default="syntax")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--optimizations", nargs="+", choices=OPTIMIZATIONS, default=OPTIMIZATIONS)
    parser.add_argument("--ptxas", type=Path, default=Path("/usr/local/cuda/bin/ptxas"))
    parser.add_argument("--nvdisasm", type=Path, default=Path("/usr/local/cuda/bin/nvdisasm"))
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()
    compile_suite(spec, suite_root, args.mode, args.work_dir or suite_root / "results" / args.mode, args.ptxas, args.nvdisasm, args.jobs, tuple(args.optimizations), args.summary_output)


def cli_negative(suite_root: Path) -> None:
    spec = _local_spec()
    parser = argparse.ArgumentParser()
    parser.add_argument("--ptxas", type=Path, default=Path("/usr/local/cuda/bin/ptxas"))
    parser.add_argument("--work-dir", type=Path, default=suite_root / "results" / "negative-probes")
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()
    check_negative(spec, suite_root, args.work_dir, args.ptxas, args.summary_output)


def cli_analyze(suite_root: Path) -> None:
    spec = _local_spec()
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=suite_root / "results" / "expanded" / "sources" / "manifest.jsonl")
    parser.add_argument("--attribution", type=Path, default=suite_root / "results" / "expanded" / "sass" / "sass_attribution.jsonl")
    parser.add_argument("--output-dir", type=Path, default=suite_root / "results" / "rule-mining")
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()
    result = analyze(spec, args.manifest, args.attribution, args.output_dir, suite_root)
    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary = {"schema_version": "tcgen05_static_mapping_summary_v1", "validation_status": "PASS", "opcode": result["opcode"], "environment": result["environment"], "forward_rule_count": result["forward_rule_count"], "inverse_signature_count": result["inverse_signature_count"], "rules_sha256": stable_hash(result["rules"]), "scope": result["scope"]}
        args.summary_output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

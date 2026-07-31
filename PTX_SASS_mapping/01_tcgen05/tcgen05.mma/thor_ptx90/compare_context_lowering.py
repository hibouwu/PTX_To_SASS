#!/usr/bin/env python3
"""Compare matched tcgen05.mma SASS across static context profiles."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re

from extract_core_sass import sass_instructions, split_text_sections
from suite_utils import reset_owned_directory, stable_hash


ROOT = Path(__file__).resolve().parent
OPTIMIZATIONS = ("O0", "O1", "O2", "O3")
NORMALIZATION_SCHEMA = "thor_sass_operation_normalization_v1"
REGISTER_PATTERNS = (
    (re.compile(r"\bUR(\d+)\b"), "UR"),
    (re.compile(r"\bUP(\d+)\b"), "UP"),
    (re.compile(r"\bR(\d+)\b"), "R"),
    (re.compile(r"\bP(\d+)\b"), "P"),
)
LABEL_RE = re.compile(r"`?\(\.L_[A-Za-z0-9_.$]+\)|\.L_[A-Za-z0-9_.$]+")
MNEMONIC_RE = re.compile(
    r"^(?:@[!A-Za-z0-9_.]+\s+)?([A-Z][A-Z0-9_.]*)\b"
)


def read_jsonl(path: Path) -> list[dict]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError(f"empty JSONL input: {path}")
    return rows


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_operations(operations: list[str]) -> list[str]:
    register_maps: dict[str, dict[str, int]] = defaultdict(dict)
    normalized_operations = []
    for operation in operations:
        normalized = LABEL_RE.sub("LABEL", operation)
        for pattern, register_class in REGISTER_PATTERNS:
            register_map = register_maps[register_class]

            def replace_register(
                match: re.Match,
                *,
                current_map: dict[str, int] = register_map,
                current_class: str = register_class,
            ) -> str:
                number = match.group(1)
                if number not in current_map:
                    current_map[number] = len(current_map)
                return f"{current_class}{{{current_map[number]}}}"

            normalized = pattern.sub(replace_register, normalized)
        normalized_operations.append(" ".join(normalized.split()))
    return normalized_operations


def normalize_operation(operation: str) -> str:
    return normalize_operations([operation])[0]


def operation_mnemonic(operation: str) -> str:
    match = MNEMONIC_RE.match(operation)
    if match is None:
        raise ValueError(f"cannot parse SASS mnemonic: {operation!r}")
    return match.group(1)


def changed_top_level_groups(baseline: dict, treatment: dict) -> list[str]:
    keys = sorted(set(baseline) | set(treatment))
    return [key for key in keys if baseline.get(key) != treatment.get(key)]


def index_unique(
    rows: list[dict],
    key_fields: tuple[str, ...],
    label: str,
) -> dict[tuple, dict]:
    result = {}
    for row in rows:
        key = tuple(row[field] for field in key_fields)
        if key in result:
            raise ValueError(f"duplicate {label} key: {key}")
        result[key] = row
    return result


def kernel_metrics(
    attribution_rows: list[dict],
    sass_dir: Path,
) -> dict[tuple[str, str], dict]:
    rows_by_artifact: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in attribution_rows:
        rows_by_artifact[(row["source_shard"], row["optimization"])].append(row)

    metrics = {}
    for (source_shard, optimization), rows in sorted(rows_by_artifact.items()):
        sass_path = (
            sass_dir / "raw" / f"{Path(source_shard).stem}_{optimization}.sass"
        )
        if not sass_path.is_file():
            raise ValueError(f"missing raw SASS: {sass_path}")
        sections = split_text_sections(sass_path.read_text(encoding="utf-8"))
        for row in rows:
            kernel = row["kernel"]
            section = sections.get(kernel)
            if section is None:
                raise ValueError(f"{sass_path}: missing kernel section {kernel}")
            instructions = sass_instructions(section)
            if not instructions:
                raise ValueError(f"{sass_path}: empty kernel section {kernel}")
            operations = [item["operation"] for item in instructions]
            normalized = normalize_operations(operations)
            mnemonics = [operation_mnemonic(item) for item in operations]
            key = (row["source_implementation_id"], optimization)
            if key in metrics:
                raise ValueError(f"duplicate kernel metrics key: {key}")
            metrics[key] = {
                "instruction_count": len(instructions),
                "exact_sequence_hash": stable_hash(
                    [
                        {
                            "offset": item["offset"],
                            "operation": item["operation"],
                            "encoding_words": item["encoding_words"],
                        }
                        for item in instructions
                    ]
                ),
                "normalized_sequence_hash": stable_hash(
                    {
                        "schema": NORMALIZATION_SCHEMA,
                        "operations": normalized,
                    }
                ),
                "mnemonic_sequence_hash": stable_hash(mnemonics),
                "mnemonic_counts": dict(sorted(Counter(mnemonics).items())),
            }
    return metrics


def counter_delta(
    baseline: dict[str, int],
    treatment: dict[str, int],
) -> tuple[dict[str, int], dict[str, int]]:
    baseline_counter = Counter(baseline)
    treatment_counter = Counter(treatment)
    added = dict(sorted((treatment_counter - baseline_counter).items()))
    removed = dict(sorted((baseline_counter - treatment_counter).items()))
    return added, removed


def compare_targets(baseline: dict, treatment: dict) -> list[dict]:
    baseline_occurrences = baseline["occurrences"]
    treatment_occurrences = treatment["occurrences"]
    if len(baseline_occurrences) != len(treatment_occurrences):
        raise ValueError(
            "matched cases have different target occurrence counts: "
            f"{baseline['case_label']} vs {treatment['case_label']}"
        )
    comparisons = []
    for baseline_item, treatment_item in zip(
        baseline_occurrences, treatment_occurrences, strict=True
    ):
        if baseline_item["occurrence_index"] != treatment_item["occurrence_index"]:
            raise ValueError("matched target occurrence indices differ")
        baseline_sass = baseline_item["sass_target"]
        treatment_sass = treatment_item["sass_target"]
        if baseline_sass is None or treatment_sass is None:
            raise ValueError("COMPLETE attribution contains a missing SASS target")
        baseline_normalized = normalize_operation(baseline_sass["operation"])
        treatment_normalized = normalize_operation(treatment_sass["operation"])
        comparisons.append(
            {
                "occurrence_index": baseline_item["occurrence_index"],
                "baseline": {
                    "ptx_instruction": baseline_item["ptx_instruction"],
                    "sass": baseline_sass,
                    "normalized_operation": baseline_normalized,
                },
                "treatment": {
                    "ptx_instruction": treatment_item["ptx_instruction"],
                    "sass": treatment_sass,
                    "normalized_operation": treatment_normalized,
                },
                "mnemonic_changed": (
                    baseline_sass["mnemonic"] != treatment_sass["mnemonic"]
                ),
                "normalized_operation_changed": (
                    baseline_normalized != treatment_normalized
                ),
                "exact_operation_changed": (
                    baseline_sass["operation"] != treatment_sass["operation"]
                ),
                "encoding_changed": (
                    baseline_sass["encoding_words"]
                    != treatment_sass["encoding_words"]
                ),
            }
        )
    return comparisons


def build_comparisons(
    manifest_rows: list[dict],
    attribution_rows: list[dict],
    metrics: dict[tuple[str, str], dict],
    baseline_profile: str,
    requested_optimizations: tuple[str, ...],
) -> tuple[list[dict], dict]:
    manifest_by_implementation = index_unique(
        manifest_rows, ("source_implementation_id",), "manifest implementation"
    )
    attribution_by_case = index_unique(
        attribution_rows,
        ("source_implementation_id", "optimization"),
        "SASS attribution",
    )
    for row in attribution_rows:
        if row["status"] != "COMPLETE":
            raise ValueError(
                f"incomplete attribution for {row['case_label']}: {row['status']}"
            )
        implementation_key = (row["source_implementation_id"],)
        if implementation_key not in manifest_by_implementation:
            raise ValueError(
                "attribution references unknown implementation: "
                f"{row['source_implementation_id']}"
            )

    manifest_by_design_profile = index_unique(
        manifest_rows,
        ("semantic_form_id", "source_variant_id", "context_profile_label"),
        "design/profile",
    )
    design_keys = sorted(
        {
            (row["semantic_form_id"], row["source_variant_id"])
            for row in manifest_rows
        }
    )
    profiles = sorted({row["context_profile_label"] for row in manifest_rows})
    if baseline_profile not in profiles:
        raise ValueError(f"baseline profile not found: {baseline_profile}")
    treatment_profiles = [
        profile for profile in profiles if profile != baseline_profile
    ]
    if not treatment_profiles:
        raise ValueError("no treatment profiles found")

    missing = []
    comparisons = []
    for semantic_form_id, source_variant_id in design_keys:
        baseline_manifest = manifest_by_design_profile.get(
            (semantic_form_id, source_variant_id, baseline_profile)
        )
        if baseline_manifest is None:
            missing.append(
                {
                    "semantic_form_id": semantic_form_id,
                    "source_variant_id": source_variant_id,
                    "profile": baseline_profile,
                }
            )
            continue
        for treatment_profile in treatment_profiles:
            treatment_manifest = manifest_by_design_profile.get(
                (semantic_form_id, source_variant_id, treatment_profile)
            )
            if treatment_manifest is None:
                missing.append(
                    {
                        "semantic_form_id": semantic_form_id,
                        "source_variant_id": source_variant_id,
                        "profile": treatment_profile,
                    }
                )
                continue
            changed_groups = changed_top_level_groups(
                baseline_manifest["static_context_assignment"],
                treatment_manifest["static_context_assignment"],
            )
            if not changed_groups:
                raise ValueError(
                    f"{treatment_profile} does not differ from baseline for "
                    f"{treatment_manifest['case_label']}"
                )
            for optimization in requested_optimizations:
                baseline_key = (
                    baseline_manifest["source_implementation_id"],
                    optimization,
                )
                treatment_key = (
                    treatment_manifest["source_implementation_id"],
                    optimization,
                )
                baseline_attribution = attribution_by_case.get(baseline_key)
                treatment_attribution = attribution_by_case.get(treatment_key)
                if baseline_attribution is None or treatment_attribution is None:
                    missing.append(
                        {
                            "semantic_form_id": semantic_form_id,
                            "source_variant_id": source_variant_id,
                            "profile": treatment_profile,
                            "optimization": optimization,
                            "missing": (
                                "baseline_attribution"
                                if baseline_attribution is None
                                else "treatment_attribution"
                            ),
                        }
                    )
                    continue
                baseline_metrics = metrics.get(baseline_key)
                treatment_metrics = metrics.get(treatment_key)
                if baseline_metrics is None or treatment_metrics is None:
                    raise ValueError("missing parsed kernel metrics")
                target_comparisons = compare_targets(
                    baseline_attribution, treatment_attribution
                )
                added, removed = counter_delta(
                    baseline_metrics["mnemonic_counts"],
                    treatment_metrics["mnemonic_counts"],
                )
                comparisons.append(
                    {
                        "semantic_form_id": semantic_form_id,
                        "source_variant_id": source_variant_id,
                        "optimization": optimization,
                        "baseline_profile": baseline_profile,
                        "treatment_profile": treatment_profile,
                        "changed_context_groups": changed_groups,
                        "context_changes": {
                            group: {
                                "baseline": baseline_manifest[
                                    "static_context_assignment"
                                ].get(group),
                                "treatment": treatment_manifest[
                                    "static_context_assignment"
                                ].get(group),
                            }
                            for group in changed_groups
                        },
                        "is_joint_treatment": len(changed_groups) > 1,
                        "baseline_case": {
                            "case_label": baseline_manifest["case_label"],
                            "source_implementation_id": baseline_key[0],
                            "static_context_id": baseline_manifest[
                                "static_context_id"
                            ],
                        },
                        "treatment_case": {
                            "case_label": treatment_manifest["case_label"],
                            "source_implementation_id": treatment_key[0],
                            "static_context_id": treatment_manifest[
                                "static_context_id"
                            ],
                        },
                        "core": {
                            "occurrence_count": len(target_comparisons),
                            "mnemonic_changed": any(
                                item["mnemonic_changed"]
                                for item in target_comparisons
                            ),
                            "normalized_operation_changed": any(
                                item["normalized_operation_changed"]
                                for item in target_comparisons
                            ),
                            "exact_operation_changed": any(
                                item["exact_operation_changed"]
                                for item in target_comparisons
                            ),
                            "encoding_changed": any(
                                item["encoding_changed"]
                                for item in target_comparisons
                            ),
                            "occurrences": target_comparisons,
                        },
                        "kernel": {
                            "baseline_instruction_count": baseline_metrics[
                                "instruction_count"
                            ],
                            "treatment_instruction_count": treatment_metrics[
                                "instruction_count"
                            ],
                            "instruction_count_delta": (
                                treatment_metrics["instruction_count"]
                                - baseline_metrics["instruction_count"]
                            ),
                            "exact_sequence_changed": (
                                baseline_metrics["exact_sequence_hash"]
                                != treatment_metrics["exact_sequence_hash"]
                            ),
                            "normalized_sequence_changed": (
                                baseline_metrics["normalized_sequence_hash"]
                                != treatment_metrics["normalized_sequence_hash"]
                            ),
                            "mnemonic_sequence_changed": (
                                baseline_metrics["mnemonic_sequence_hash"]
                                != treatment_metrics["mnemonic_sequence_hash"]
                            ),
                            "baseline_normalized_sequence_hash": baseline_metrics[
                                "normalized_sequence_hash"
                            ],
                            "treatment_normalized_sequence_hash": treatment_metrics[
                                "normalized_sequence_hash"
                            ],
                            "mnemonics_added": added,
                            "mnemonics_removed": removed,
                        },
                    }
                )
    return comparisons, {
        "profiles": profiles,
        "treatment_profiles": treatment_profiles,
        "design_key_count": len(design_keys),
        "missing": missing,
    }


def summarize(comparisons: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, tuple[str, ...]], list[dict]] = defaultdict(list)
    for row in comparisons:
        grouped[
            (
                row["treatment_profile"],
                row["optimization"],
                tuple(row["changed_context_groups"]),
            )
        ].append(row)
    summaries = []
    for (profile, optimization, changed_groups), rows in sorted(grouped.items()):
        count = len(rows)

        def changed(path: tuple[str, str]) -> int:
            return sum(bool(row[path[0]][path[1]]) for row in rows)

        summaries.append(
            {
                "treatment_profile": profile,
                "optimization": optimization,
                "comparison_count": count,
                "changed_context_groups": "+".join(changed_groups),
                "joint_treatment_count": sum(
                    row["is_joint_treatment"] for row in rows
                ),
                "core_mnemonic_changed_count": changed(
                    ("core", "mnemonic_changed")
                ),
                "core_normalized_operation_changed_count": changed(
                    ("core", "normalized_operation_changed")
                ),
                "core_exact_operation_changed_count": changed(
                    ("core", "exact_operation_changed")
                ),
                "core_encoding_changed_count": changed(
                    ("core", "encoding_changed")
                ),
                "kernel_normalized_sequence_changed_count": changed(
                    ("kernel", "normalized_sequence_changed")
                ),
                "kernel_mnemonic_sequence_changed_count": changed(
                    ("kernel", "mnemonic_sequence_changed")
                ),
                "kernel_instruction_count_changed_count": sum(
                    row["kernel"]["instruction_count_delta"] != 0 for row in rows
                ),
            }
        )
    return summaries


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("cannot write empty summary")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def percent(value: int, denominator: int) -> str:
    return f"{value} ({value / denominator:.1%})"


def write_markdown(
    path: Path,
    summaries: list[dict],
    metadata: dict,
) -> None:
    lines = [
        "# tcgen05.mma 上下文差分报告",
        "",
        "## 结果概览",
        "",
        f"- 基线：`{metadata['baseline_profile']}`",
        f"- 配对设计数：{metadata['design_key_count']}",
        f"- 总比较数：{metadata['comparison_count']}",
        f"- 优化级：{', '.join(metadata['optimizations'])}",
        f"- SASS 规范化版本：`{NORMALIZATION_SCHEMA}`",
        "",
        "核心变化忽略指令地址和具体寄存器编号，但保留助记符、修饰、",
        "操作数类别、立即数和操作数结构。kernel 变化比较完整规范化指令序列。",
        "",
        "## 分上下文统计",
        "",
        "| 上下文 | 实际改变的 CTX | 优化 | 配对数 | 核心助记符变化 | "
        "核心规范形变化 | kernel 规范序列变化 | kernel 指令数变化 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        count = row["comparison_count"]
        lines.append(
            f"| `{row['treatment_profile']}` | "
            f"`{row['changed_context_groups']}` | "
            f"{row['optimization']} | {count} | "
            f"{percent(row['core_mnemonic_changed_count'], count)} | "
            f"{percent(row['core_normalized_operation_changed_count'], count)} | "
            f"{percent(row['kernel_normalized_sequence_changed_count'], count)} | "
            f"{percent(row['kernel_instruction_count_changed_count'], count)} |"
        )
    lines.extend(["", "## 处理解释", ""])
    by_profile: dict[str, list[dict]] = defaultdict(list)
    for row in summaries:
        by_profile[row["treatment_profile"]].append(row)
    for profile, rows in sorted(by_profile.items()):
        group_sets = sorted({item["changed_context_groups"] for item in rows})
        joint_count = sum(item["joint_treatment_count"] for item in rows)
        lines.append(
            f"- `{profile}`：改变的 CTX 组为 `{'; '.join(group_sets)}`。"
            + (
                "其中存在联合处理，只能解释为联合效应。"
                if joint_count
                else "这是单个顶层 CTX 组的处理。"
            )
        )
    lines.extend(
        [
            "",
            "## 口径",
            "",
            "- `core` 只比较已经归属的 MMA 核心指令。",
            "- `kernel` 比较整个 kernel，因此包含参数装载、谓词、分支、",
            "  操作数准备和完成指令。",
            "- `encoding_changed` 保留具体寄存器编码，不能单独解释为",
            "  指令选择发生变化。",
            "- 本报告是静态代码生成差分，不是运行时语义或性能结论。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--sass-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-profile", default="runtime_zero")
    parser.add_argument(
        "--optimizations",
        nargs="+",
        choices=OPTIMIZATIONS,
        default=OPTIMIZATIONS,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = reset_owned_directory(
        args.output_dir,
        owner="thor_tcgen05_context_comparison",
        protected=(ROOT,),
    )
    manifest_path = args.source_dir / "manifest.jsonl"
    attribution_path = args.sass_dir / "sass_attribution.jsonl"
    manifest_rows = read_jsonl(manifest_path)
    attribution_rows = read_jsonl(attribution_path)
    requested_optimizations = tuple(args.optimizations)
    attribution_rows = [
        row
        for row in attribution_rows
        if row["optimization"] in requested_optimizations
    ]
    if not attribution_rows:
        raise ValueError("no attribution rows for requested optimization levels")
    metrics = kernel_metrics(attribution_rows, args.sass_dir)
    comparisons, design_metadata = build_comparisons(
        manifest_rows,
        attribution_rows,
        metrics,
        args.baseline_profile,
        requested_optimizations,
    )
    if design_metadata["missing"]:
        missing_path = output_dir / "missing_pairs.json"
        missing_path.write_text(
            json.dumps(design_metadata["missing"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise ValueError(
            f"incomplete matched design: {len(design_metadata['missing'])} missing; "
            f"see {missing_path}"
        )
    expected_comparisons = (
        design_metadata["design_key_count"]
        * len(design_metadata["treatment_profiles"])
        * len(requested_optimizations)
    )
    if len(comparisons) != expected_comparisons:
        raise ValueError(
            f"comparison count mismatch: expected {expected_comparisons}, "
            f"got {len(comparisons)}"
        )

    differences_path = output_dir / "context_differences.jsonl"
    with differences_path.open("w", encoding="utf-8") as handle:
        for row in comparisons:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    summaries = summarize(comparisons)
    summary_path = output_dir / "context_summary.csv"
    write_csv(summary_path, summaries)
    report_path = output_dir / "context_report.md"
    metadata = {
        "schema_version": "thor_tcgen05_context_comparison_v1",
        "status": "COMPLETE",
        "normalization_schema": NORMALIZATION_SCHEMA,
        "baseline_profile": args.baseline_profile,
        "profiles": design_metadata["profiles"],
        "treatment_profiles": design_metadata["treatment_profiles"],
        "optimizations": list(requested_optimizations),
        "design_key_count": design_metadata["design_key_count"],
        "comparison_count": len(comparisons),
        "expected_comparison_count": expected_comparisons,
        "input_manifest_sha256": file_sha256(manifest_path),
        "input_sass_attribution_sha256": file_sha256(attribution_path),
        "differences_sha256": file_sha256(differences_path),
        "summary_sha256": file_sha256(summary_path),
        "differences_file": differences_path.name,
        "summary_file": summary_path.name,
        "report_file": report_path.name,
    }
    write_markdown(report_path, summaries, metadata)
    metadata["report_sha256"] = file_sha256(report_path)
    (output_dir / "comparison_report.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"{len(comparisons)}/{expected_comparisons} matched comparisons complete; "
        f"report: {report_path}"
    )


if __name__ == "__main__":
    main()

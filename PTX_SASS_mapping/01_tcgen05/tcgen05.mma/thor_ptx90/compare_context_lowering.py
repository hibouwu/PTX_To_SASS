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

from extract_core_sass import (
    liveness_instructions,
    liveness_matches_sass,
    sass_instructions,
    split_text_sections,
)
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
REGISTER_TOKEN_RE = re.compile(r"\b(?:UR\d+|UP\d+|R\d+|P\d+|URZ|UPT|RZ|PT)\b")
NUMBERED_REGISTER_RE = re.compile(r"^(UR|UP|R|P)(\d+)$")
GUARD_RE = re.compile(r"^@(!?)(UP\d+|P\d+|UPT|PT)\s+")
LIVE_REGISTER_CLASSES = ("gpr", "pred", "ugpr", "upred")


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


def split_operands(operand_text: str) -> list[str]:
    operands = []
    start = 0
    depth = 0
    for index, character in enumerate(operand_text):
        if character in "[({":
            depth += 1
        elif character in "])}":
            depth = max(0, depth - 1)
        elif character == "," and depth == 0:
            operands.append(operand_text[start:index].strip())
            start = index + 1
    if operand_text[start:].strip():
        operands.append(operand_text[start:].strip())
    return operands


def register_class(register: str) -> str:
    match = NUMBERED_REGISTER_RE.fullmatch(register)
    return match.group(1) if match is not None else register


def register_placement(operation: str) -> dict:
    """Describe concrete registers, register routes, and within-op aliasing."""
    guard_match = GUARD_RE.match(operation)
    guard = None
    body = operation
    if guard_match is not None:
        guard = {
            "negated": bool(guard_match.group(1)),
            "register": guard_match.group(2),
        }
        body = operation[guard_match.end() :]
    parts = body.split(maxsplit=1)
    operands = split_operands(parts[1]) if len(parts) == 2 else []
    concrete_operands = [
        REGISTER_TOKEN_RE.findall(operand) for operand in operands
    ]

    class_guard = (
        {
            "negated": guard["negated"],
            "register": register_class(guard["register"]),
        }
        if guard is not None
        else None
    )
    class_operands = [
        [register_class(register) for register in registers]
        for registers in concrete_operands
    ]

    alias_maps: dict[str, dict[str, int]] = defaultdict(dict)

    def alias(register: str) -> str:
        register_kind = register_class(register)
        if NUMBERED_REGISTER_RE.fullmatch(register) is None:
            return register_kind
        register_map = alias_maps[register_kind]
        if register not in register_map:
            register_map[register] = len(register_map)
        return f"{register_kind}{{{register_map[register]}}}"

    alias_guard = (
        {
            "negated": guard["negated"],
            "register": alias(guard["register"]),
        }
        if guard is not None
        else None
    )
    alias_operands = [
        [alias(register) for register in registers]
        for registers in concrete_operands
    ]
    return {
        "concrete": {"guard": guard, "operands": concrete_operands},
        "classes": {"guard": class_guard, "operands": class_operands},
        "aliases": {"guard": alias_guard, "operands": alias_operands},
    }


def register_inventory(operations: list[str]) -> dict:
    registers: dict[str, set[int]] = {
        register_kind: set() for register_kind in ("R", "P", "UR", "UP")
    }
    for operation in operations:
        for token in REGISTER_TOKEN_RE.findall(operation):
            match = NUMBERED_REGISTER_RE.fullmatch(token)
            if match is not None:
                registers[match.group(1)].add(int(match.group(2)))
    serialized = {
        register_kind: sorted(numbers)
        for register_kind, numbers in registers.items()
    }
    return {
        "referenced_count": {
            register_kind: len(numbers)
            for register_kind, numbers in serialized.items()
        },
        "max_referenced_index": {
            register_kind: max(numbers) if numbers else None
            for register_kind, numbers in serialized.items()
        },
        "set_hash": stable_hash(serialized),
    }


def live_register_delta(baseline: dict, treatment: dict) -> dict:
    return {
        register_kind: treatment[register_kind] - baseline[register_kind]
        for register_kind in LIVE_REGISTER_CLASSES
    }


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
        liveness_path = (
            sass_dir
            / "liveness"
            / f"{Path(source_shard).stem}_{optimization}.sass"
        )
        if not liveness_path.is_file():
            raise ValueError(f"missing liveness SASS: {liveness_path}")
        liveness_sections = split_text_sections(
            liveness_path.read_text(encoding="utf-8")
        )
        for row in rows:
            kernel = row["kernel"]
            section = sections.get(kernel)
            if section is None:
                raise ValueError(f"{sass_path}: missing kernel section {kernel}")
            instructions = sass_instructions(section)
            if not instructions:
                raise ValueError(f"{sass_path}: empty kernel section {kernel}")
            liveness_section = liveness_sections.get(kernel)
            if liveness_section is None:
                raise ValueError(
                    f"{liveness_path}: missing kernel section {kernel}"
                )
            liveness = liveness_instructions(liveness_section)
            if not liveness_matches_sass(instructions, liveness):
                raise ValueError(
                    f"{liveness_path}: analyzed instructions differ for {kernel}"
                )
            operations = [item["operation"] for item in instructions]
            normalized = normalize_operations(operations)
            mnemonics = [operation_mnemonic(item) for item in operations]
            inventory = register_inventory(operations)
            peak_live = {
                register_kind: max(
                    item["live_registers"][register_kind] for item in liveness
                )
                for register_kind in LIVE_REGISTER_CLASSES
            }
            spill_load_count = sum(
                mnemonic.startswith("LDL") for mnemonic in mnemonics
            )
            spill_store_count = sum(
                mnemonic.startswith("STL") for mnemonic in mnemonics
            )
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
                "peak_live_registers": peak_live,
                "register_inventory": inventory,
                "local_memory_indicators": {
                    "load_instruction_count": spill_load_count,
                    "store_instruction_count": spill_store_count,
                    "instruction_count": spill_load_count + spill_store_count,
                },
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
        baseline_placement = register_placement(baseline_sass["operation"])
        treatment_placement = register_placement(treatment_sass["operation"])
        physical_register_changed = (
            baseline_placement["concrete"] != treatment_placement["concrete"]
        )
        register_class_changed = (
            baseline_placement["classes"] != treatment_placement["classes"]
        )
        alias_pattern_changed = (
            baseline_placement["aliases"] != treatment_placement["aliases"]
        )
        baseline_live = baseline_sass.get("live_registers")
        treatment_live = treatment_sass.get("live_registers")
        if baseline_live is None or treatment_live is None:
            raise ValueError("COMPLETE attribution contains missing liveness data")
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
                "allocation": {
                    "physical_register_changed": physical_register_changed,
                    "register_class_changed": register_class_changed,
                    "alias_pattern_changed": alias_pattern_changed,
                    "renumber_only": (
                        physical_register_changed
                        and not register_class_changed
                        and not alias_pattern_changed
                    ),
                    "live_register_delta": live_register_delta(
                        baseline_live, treatment_live
                    ),
                    "live_registers_changed": baseline_live != treatment_live,
                },
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
    design_treatment_pair_count = 0
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
        applicable_treatments = sorted(
            row["context_profile_label"]
            for row in manifest_rows
            if row["semantic_form_id"] == semantic_form_id
            and row["source_variant_id"] == source_variant_id
            and row["context_profile_label"] != baseline_profile
        )
        design_treatment_pair_count += len(applicable_treatments)
        for treatment_profile in applicable_treatments:
            treatment_manifest = manifest_by_design_profile.get(
                (semantic_form_id, source_variant_id, treatment_profile)
            )
            if treatment_manifest is None:
                raise AssertionError("applicable treatment index is inconsistent")
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
                physical_register_changed = any(
                    item["allocation"]["physical_register_changed"]
                    for item in target_comparisons
                )
                register_class_changed = any(
                    item["allocation"]["register_class_changed"]
                    for item in target_comparisons
                )
                alias_pattern_changed = any(
                    item["allocation"]["alias_pattern_changed"]
                    for item in target_comparisons
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
                            "physical_register_changed": physical_register_changed,
                            "register_class_changed": register_class_changed,
                            "alias_pattern_changed": alias_pattern_changed,
                            "renumber_only": (
                                physical_register_changed
                                and not register_class_changed
                                and not alias_pattern_changed
                            ),
                            "target_live_registers_changed": any(
                                item["allocation"]["live_registers_changed"]
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
                            "baseline_peak_live_registers": baseline_metrics[
                                "peak_live_registers"
                            ],
                            "treatment_peak_live_registers": treatment_metrics[
                                "peak_live_registers"
                            ],
                            "peak_live_register_delta": live_register_delta(
                                baseline_metrics["peak_live_registers"],
                                treatment_metrics["peak_live_registers"],
                            ),
                            "peak_live_registers_changed": (
                                baseline_metrics["peak_live_registers"]
                                != treatment_metrics["peak_live_registers"]
                            ),
                            "baseline_referenced_registers": {
                                key: value
                                for key, value in baseline_metrics[
                                    "register_inventory"
                                ].items()
                                if key != "set_hash"
                            },
                            "treatment_referenced_registers": {
                                key: value
                                for key, value in treatment_metrics[
                                    "register_inventory"
                                ].items()
                                if key != "set_hash"
                            },
                            "referenced_register_set_changed": (
                                baseline_metrics["register_inventory"][
                                    "set_hash"
                                ]
                                != treatment_metrics["register_inventory"][
                                    "set_hash"
                                ]
                            ),
                            "baseline_local_memory_indicators": baseline_metrics[
                                "local_memory_indicators"
                            ],
                            "treatment_local_memory_indicators": treatment_metrics[
                                "local_memory_indicators"
                            ],
                            "local_memory_indicators_changed": (
                                baseline_metrics["local_memory_indicators"]
                                != treatment_metrics["local_memory_indicators"]
                            ),
                        },
                    }
                )
    return comparisons, {
        "profiles": profiles,
        "treatment_profiles": treatment_profiles,
        "design_key_count": len(design_keys),
        "design_treatment_pair_count": design_treatment_pair_count,
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
                "core_physical_register_changed_count": changed(
                    ("core", "physical_register_changed")
                ),
                "core_renumber_only_count": changed(
                    ("core", "renumber_only")
                ),
                "core_register_class_changed_count": changed(
                    ("core", "register_class_changed")
                ),
                "core_alias_pattern_changed_count": changed(
                    ("core", "alias_pattern_changed")
                ),
                "target_live_registers_changed_count": changed(
                    ("core", "target_live_registers_changed")
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
                "kernel_peak_live_registers_changed_count": changed(
                    ("kernel", "peak_live_registers_changed")
                ),
                "kernel_referenced_register_set_changed_count": changed(
                    ("kernel", "referenced_register_set_changed")
                ),
                "kernel_local_memory_indicators_changed_count": changed(
                    ("kernel", "local_memory_indicators_changed")
                ),
            }
        )
    return summaries


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("cannot write empty summary")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), lineterminator="\n"
        )
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
        "## 实验配置",
        "",
        f"- 基线：`{metadata['baseline_profile']}`",
        f"- 配对设计数：{metadata['design_key_count']}",
        f"- 总比较数：{metadata['comparison_count']}",
        f"- 编译优化级：{'、'.join(metadata['optimizations'])}",
        f"- SASS 规范化版本：`{NORMALIZATION_SCHEMA}`",
        "",
        "核心变化比较时忽略指令地址和具体寄存器编号，保留助记符、修饰符、操作数类别、立即数和操作数结构。kernel 变化比较完整规范化指令序列。寄存器表单独保留具体编号、R/UR/P/UP 类别、寄存器复用关系和 `nvdisasm` 给出的逐指令活跃寄存器计数。",
        "",
        "## 分上下文统计",
        "",
        "下表列出每种上下文配置文件和优化级的配对数量及各项变化情况。核心助记符变化栏在所有行中均为 0，说明上下文不改变核心 MMA 的助记符选择。",
        "",
        "| 上下文 | 改变的 CTX 组 | 优化 | 配对数 | 核心助记符变化 | "
        "核心规范形变化 | kernel 规范序列变化 | kernel 指令数变化 |",
        "|---|---|---|---|---|---|---|---|",
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
    lines.extend(
        [
            "",
            "## 寄存器分配差分",
            "",
            "下表列出寄存器层面的差分统计。",
            "",
            "| 上下文 | 改变的 CTX | 优化 | 配对数 | 核心寄存器布局变化 | "
            "仅重编号 | 类别变化 | 别名关系变化 | 核心处活跃数变化 | "
            "kernel 峰值活跃数变化 | kernel 引用集合变化 | 本地内存指令变化 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in summaries:
        count = row["comparison_count"]
        lines.append(
            f"| `{row['treatment_profile']}` | "
            f"`{row['changed_context_groups']}` | "
            f"{row['optimization']} | {count} | "
            f"{percent(row['core_physical_register_changed_count'], count)} | "
            f"{percent(row['core_renumber_only_count'], count)} | "
            f"{percent(row['core_register_class_changed_count'], count)} | "
            f"{percent(row['core_alias_pattern_changed_count'], count)} | "
            f"{percent(row['target_live_registers_changed_count'], count)} | "
            f"{percent(row['kernel_peak_live_registers_changed_count'], count)} | "
            f"{percent(row['kernel_referenced_register_set_changed_count'], count)} | "
            f"{percent(row['kernel_local_memory_indicators_changed_count'], count)} |"
        )
    lines.extend(["", "## 各种上下文配置文件的含义", ""])
    by_profile: dict[str, list[dict]] = defaultdict(list)
    for row in summaries:
        by_profile[row["treatment_profile"]].append(row)
    for profile, rows in sorted(by_profile.items()):
        group_sets = sorted({item["changed_context_groups"] for item in rows})
        joint_count = sum(item["joint_treatment_count"] for item in rows)
        explanations = {
            "commit_completion": "单独改变顶层上下文组 completion。",
            "derived_producers": "单独改变生产者链。",
            "enable_false": "单独改变 D 累加使能常量。",
            "enable_true_mask_ones": "这是一个联合处理配置，存在联合效应。",
            "guard_negative": "使用负 guard。",
            "guard_positive": "使用正 guard。",
            "lane0_issuer": "限制 lane 0 为发射线程。",
            "lane31_issuer": "限制 lane 31 为发射线程。",
            "dynamic_lane_issuer": "由 kernel 参数选择发射 lane。",
            "thread0_issuer": "限制 CTA thread 0 为发射线程。",
            "compound_predicated_issuer": "用 lane 0 与参数谓词的合取直接保护目标指令。",
            "nonidentity_producers": "用参数 delta 构造不能被消除的算术 producer。",
            "branched_producers": "在条件基本块中选择直接参数或 delta 派生 producer。",
            "global_load_producers": "从 global-memory load 生成全部目标操作数。",
            "predicate_index_up0": "释放 enable 的 UP0 后定向观察核心 guard 的 UP0 编码。",
            "predicate_pressure_1": "用统一谓词活跃压力定向观察核心 guard 的 UP1 编码。",
            "predicate_pressure_2": "用统一谓词活跃压力定向观察核心 guard 的 UP2 编码。",
            "predicate_pressure_3": "用统一谓词活跃压力定向观察核心 guard 的 UP3 编码。",
            "predicate_pressure_4": "用统一谓词活跃压力定向观察核心 guard 的 UP4 编码。",
            "predicate_pressure_5": "用统一谓词活跃压力定向观察核心 guard 的 UP5 编码。",
            "predicate_pressure_6": "用统一谓词活跃压力定向观察核心 guard 的 UP6 编码。",
            "enable_index_sweep": "七条代表性核心指令分别使用七个同时活跃的 enable 谓词，以恢复 enable-index 字段。",
        }
        lines.append(f"- `{profile}`：改变 `{'; '.join(group_sets)}` 上下文组。{explanations.get(profile, '其中存在联合处理，只能解释为联合效应。' if joint_count else '单独改变一个顶层上下文组。')}")
    lines.extend(
        [
            "",
            "## 统计口径",
            "",
            "- `core`：只比较已经归属的 MMA 核心指令。",
            "- `kernel`：比较整个 kernel，包含参数装载、谓词、分支、操作数准备和完成指令。",
            "- `encoding_changed`：保留具体寄存器编码，不能单独解释为指令选择发生变化。",
            "- `仅重编号`：核心 MMA 使用的具体寄存器号改变，但 R/UR/P/UP 路径和操作数之间的寄存器复用关系不变。",
            "- `类别变化`：区分普通寄存器与统一寄存器以及谓词路径，也区分 RZ、URZ、PT、UPT 等特殊寄存器。",
            "- 活跃寄存器数来自 `nvdisasm --life-range-mode count` 的静态数据流结果。kernel 引用过的寄存器集合不等于硬件分配上限。",
            "- `LDL*`/`STL*` 被记为本地内存指令指标，能提示潜在的寄存器溢出（spill），但仅凭指令名不能断言一定由溢出造成。",
            "- 本报告只描述静态 PTX → SASS 代码生成差分。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--sass-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--report-output",
        type=Path,
        help="optional path for publishing the final human-readable report",
    )
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
        design_metadata["design_treatment_pair_count"]
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
        "schema_version": "thor_tcgen05_context_comparison_v3",
        "status": "COMPLETE",
        "normalization_schema": NORMALIZATION_SCHEMA,
        "baseline_profile": args.baseline_profile,
        "profiles": design_metadata["profiles"],
        "treatment_profiles": design_metadata["treatment_profiles"],
        "optimizations": list(requested_optimizations),
        "design_key_count": design_metadata["design_key_count"],
        "design_treatment_pair_count": design_metadata[
            "design_treatment_pair_count"
        ],
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
    if args.report_output is not None:
        published_report_path = args.report_output.expanduser().resolve()
        published_report_path.parent.mkdir(parents=True, exist_ok=True)
        if published_report_path != report_path.resolve():
            write_markdown(published_report_path, summaries, metadata)
    metadata["report_sha256"] = file_sha256(report_path)
    (output_dir / "comparison_report.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"{len(comparisons)}/{expected_comparisons} matched comparisons complete; "
        f"report: {report_path}"
        + (
            f"; published: {args.report_output.expanduser().resolve()}"
            if args.report_output is not None
            else ""
        )
    )


if __name__ == "__main__":
    main()

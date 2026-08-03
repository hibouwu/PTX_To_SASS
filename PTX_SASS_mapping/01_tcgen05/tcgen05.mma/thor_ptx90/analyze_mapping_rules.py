#!/usr/bin/env python3
"""Mine predictive and inverse tcgen05.mma rules from generated evidence."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
from pathlib import Path
import re

from compare_context_lowering import normalize_operation
from suite_utils import reset_owned_directory


ROOT = Path(__file__).resolve().parent
DIRECT_GUARD_RE = re.compile(r"^@!?(?:UP\d+|P\d+|UPT|PT)\s+")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_guard_outcome(features: dict) -> str:
    first_occurrence = features["step_count"] == 2 and (
        features["variant"] in {"mma.sp", "mma.ws.sp"}
        or (
            features["kind"] in {"f16", "tf32", "f8f6f4", "i8"}
            and not features["zero_column_mask"]
        )
    )
    return "first_occurrence_core_predication" if first_occurrence else "external_control_flow"


def expected_issuer_outcome(features: dict) -> str:
    renumber_only = features["a_form"] == "tmem_address" and (
        (
            features["variant"] == "mma.sp"
            and features["kind"] in {"mxf4", "mxf4nvf4", "mxf8f6f4"}
        )
        or (
            features["variant"] == "mma.ws.sp"
            and features["zero_column_mask"]
        )
    )
    return "renumber_only" if renumber_only else "stable_layout"


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def stable_value(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def display_value(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple):
        return "/".join(str(item) for item in value) if value else "—"
    return str(value)


def case_features(manifest: dict) -> dict:
    semantic = manifest["semantic_form"]
    source = manifest["source_variant"]
    steps = semantic["collector_steps"]
    return {
        "variant": semantic["variant"],
        "cta_group": semantic["cta_group"],
        "kind": semantic["kind"],
        "a_form": semantic["a_form"],
        "scale_vector_semantics": semantic["scale_vector_semantics"],
        "zero_column_mask": semantic["zero_column_mask"],
        "step_count": len(steps),
        "collector_ops": tuple(step["collector_op"] for step in steps),
        "collector_buffers": tuple(step["collector_buffer"] for step in steps),
        "ashift_pattern": tuple(step["ashift"] for step in steps),
        "collector_spelling": source["collector_spelling"],
        "scale_vector_spelling": source["scale_vector_spelling"],
    }


FEATURE_KEYS = tuple(
    (
        "variant",
        "cta_group",
        "kind",
        "a_form",
        "scale_vector_semantics",
        "zero_column_mask",
        "step_count",
        "collector_ops",
        "collector_buffers",
        "ashift_pattern",
        "collector_spelling",
        "scale_vector_spelling",
    )
)


def minimal_exact_predictors(rows: list[dict], max_size: int = 4) -> list[tuple[str, ...]]:
    for size in range(1, max_size + 1):
        predictors = []
        for keys in combinations(FEATURE_KEYS, size):
            outcomes = defaultdict(set)
            for row in rows:
                outcomes[tuple(stable_value(row["features"][key]) for key in keys)].add(
                    row["outcome"]
                )
            if all(len(labels) == 1 for labels in outcomes.values()):
                predictors.append(keys)
        if predictors:
            return predictors
    return []


def predictor_groups(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    groups = defaultdict(Counter)
    for row in rows:
        values = tuple(row["features"][key] for key in keys)
        groups[values][row["outcome"]] += 1
    return [
        {
            "values": {key: value for key, value in zip(keys, values, strict=True)},
            "outcomes": dict(sorted(counts.items())),
        }
        for values, counts in sorted(groups.items(), key=lambda item: stable_value(item[0]))
    ]


def classify_context_rules(
    differences_path: Path,
    manifest_by_implementation: dict[str, dict],
) -> tuple[list[dict], list[dict], dict]:
    guard_rows = []
    issuer_rows = []
    guard_polarity_consistency = defaultdict(dict)
    for row in read_jsonl(differences_path):
        if row["optimization"] != "O3":
            continue
        profile = row["treatment_profile"]
        if profile not in {"guard_positive", "guard_negative", "lane0_issuer"}:
            continue
        implementation_id = row["treatment_case"]["source_implementation_id"]
        manifest = manifest_by_implementation[implementation_id]
        features = case_features(manifest)
        if profile.startswith("guard_"):
            operations = [
                occurrence["treatment"]["sass"]["operation"]
                for occurrence in row["core"]["occurrences"]
            ]
            direct_count = sum(bool(DIRECT_GUARD_RE.match(op)) for op in operations)
            guard_shape = tuple(bool(DIRECT_GUARD_RE.match(op)) for op in operations)
            if guard_shape == (True, False):
                outcome = "first_occurrence_core_predication"
            elif direct_count == 0:
                outcome = "external_control_flow"
            else:
                outcome = "unexpected_guard_shape"
            guard_rows.append(
                {
                    "profile": profile,
                    "semantic_form_id": row["semantic_form_id"],
                    "source_variant_id": row["source_variant_id"],
                    "case_label": row["treatment_case"]["case_label"],
                    "features": features,
                    "outcome": outcome,
                    "guard_shape": guard_shape,
                }
            )
            guard_polarity_consistency[
                (row["semantic_form_id"], row["source_variant_id"])
            ][profile] = outcome
        else:
            issuer_rows.append(
                {
                    "semantic_form_id": row["semantic_form_id"],
                    "source_variant_id": row["source_variant_id"],
                    "case_label": row["treatment_case"]["case_label"],
                    "features": features,
                    "outcome": (
                        "renumber_only" if row["core"]["renumber_only"] else "stable_layout"
                    ),
                }
            )
    mismatches = [
        {"design": key, "outcomes": value}
        for key, value in guard_polarity_consistency.items()
        if len(set(value.values())) != 1 or len(value) != 2
    ]
    positive_guard_rows = [row for row in guard_rows if row["profile"] == "guard_positive"]
    return positive_guard_rows, issuer_rows, {"polarity_mismatches": mismatches}


INVERSE_FIELDS = (
    "opcode_variant",
    "weight_stationary",
    "sparse",
    "cta_group",
    "kind",
    "a_form",
    "scale_vector_semantics",
    "scale_vector_spelling",
    "zero_column_mask",
    "collector_op",
    "collector_buffer",
    "ashift",
    "collector_spelling",
)


def occurrence_fields(manifest: dict, occurrence_index: int) -> dict:
    semantic = manifest["semantic_form"]
    step = semantic["collector_steps"][occurrence_index]
    source = manifest["source_variant"]
    return {
        "opcode_variant": f"tcgen05.{semantic['variant']}",
        "weight_stationary": ".ws" in semantic["variant"],
        "sparse": ".sp" in semantic["variant"],
        "cta_group": semantic["cta_group"],
        "kind": semantic["kind"],
        "a_form": semantic["a_form"],
        "scale_vector_semantics": semantic["scale_vector_semantics"],
        "scale_vector_spelling": source["scale_vector_spelling"],
        "zero_column_mask": semantic["zero_column_mask"],
        "collector_op": step["collector_op"],
        "collector_buffer": step["collector_buffer"],
        "ashift": step["ashift"],
        "collector_spelling": source["collector_spelling"],
    }


def analyze_inverse_mapping(
    attribution_path: Path,
    manifest_by_implementation: dict[str, dict],
) -> dict:
    records = []
    for attribution in read_jsonl(attribution_path):
        if attribution["optimization"] != "O3":
            continue
        manifest = manifest_by_implementation[attribution["source_implementation_id"]]
        if manifest["context_profile_label"] != "runtime_zero":
            continue
        for occurrence in attribution["occurrences"]:
            sass = occurrence["sass_target"]
            if sass is None:
                raise ValueError(f"missing SASS target in {attribution['case_label']}")
            records.append(
                {
                    "witness_id": (
                        f"{attribution['case_label']}:O3:"
                        f"{occurrence['occurrence_index']}"
                    ),
                    "case_label": attribution["case_label"],
                    "source_implementation_id": attribution[
                        "source_implementation_id"
                    ],
                    "occurrence_index": occurrence["occurrence_index"],
                    "ptx_instruction": occurrence["ptx_instruction"],
                    "case_label": attribution["case_label"],
                    "ptx_instruction": occurrence["ptx_instruction"],
                    "sass_signature": normalize_operation(sass["operation"]),
                    "fields": occurrence_fields(manifest, occurrence["occurrence_index"]),
                }
            )
    by_signature = defaultdict(list)
    for record in records:
        by_signature[record["sass_signature"]].append(record)
    field_results = []
    for field in INVERSE_FIELDS:
        unambiguous_signatures = 0
        unambiguous_occurrences = 0
        ambiguous_values = set()
        for group in by_signature.values():
            values = {stable_value(record["fields"][field]) for record in group}
            if len(values) == 1:
                unambiguous_signatures += 1
                unambiguous_occurrences += len(group)
            else:
                ambiguous_values.update(values)
        field_results.append(
            {
                "field": field,
                "unambiguous_signature_count": unambiguous_signatures,
                "signature_count": len(by_signature),
                "unambiguous_occurrence_count": unambiguous_occurrences,
                "occurrence_count": len(records),
                "ambiguous_values": sorted(ambiguous_values),
            }
        )
    collision_groups = []
    for signature, group in by_signature.items():
        ptx_spellings = sorted({record["ptx_instruction"] for record in group})
        field_values = {
            field: sorted({stable_value(record["fields"][field]) for record in group})
            for field in INVERSE_FIELDS
        }
        ambiguous_fields = {
            field: values for field, values in field_values.items() if len(values) > 1
        }
        if len(ptx_spellings) > 1 or ambiguous_fields:
            collision_groups.append(
                {
                    "sass_signature": signature,
                    "occurrence_count": len(group),
                    "ptx_spelling_count": len(ptx_spellings),
                    "ptx_spellings": ptx_spellings,
                    "ambiguous_fields": ambiguous_fields,
                }
            )
    collision_groups.sort(
        key=lambda item: (
            -len(item["ambiguous_fields"]),
            -item["ptx_spelling_count"],
            item["sass_signature"],
        )
    )
    return {
        "optimization": "O3",
        "profile": "runtime_zero",
        "occurrence_count": len(records),
        "unique_ptx_instruction_count": len({record["ptx_instruction"] for record in records}),
        "sass_signature_count": len(by_signature),
        "collision_signature_count": len(collision_groups),
        "semantic_collision_signature_count": sum(
            any(
                field in item["ambiguous_fields"]
                for field in INVERSE_FIELDS
                if field not in {"scale_vector_spelling", "collector_spelling"}
            )
            for item in collision_groups
        ),
        "field_recoverability": field_results,
        "top_collision_groups": collision_groups[:12],
    }


def analyze_source_aliases(
    attribution_path: Path,
    manifest_by_implementation: dict[str, dict],
) -> dict:
    sass_by_implementation = {}
    for attribution in read_jsonl(attribution_path):
        if attribution["optimization"] != "O3":
            continue
        manifest = manifest_by_implementation[attribution["source_implementation_id"]]
        if manifest["context_profile_label"] != "runtime_zero":
            continue
        sass_by_implementation[attribution["source_implementation_id"]] = {
            "operations": tuple(
                occurrence["sass_target"]["operation"]
                for occurrence in attribution["occurrences"]
            ),
            "encodings": tuple(
                tuple(occurrence["sass_target"]["encoding_words"])
                for occurrence in attribution["occurrences"]
            ),
        }
    by_semantic_form = defaultdict(list)
    for implementation_id, manifest in manifest_by_implementation.items():
        if manifest["context_profile_label"] == "runtime_zero":
            by_semantic_form[manifest["semantic_form_id"]].append(implementation_id)
    category_counts = defaultdict(Counter)
    total = Counter()
    for implementation_ids in by_semantic_form.values():
        for left_id, right_id in combinations(sorted(implementation_ids), 2):
            left_manifest = manifest_by_implementation[left_id]
            right_manifest = manifest_by_implementation[right_id]
            changed = tuple(
                field
                for field in ("collector_spelling", "scale_vector_spelling")
                if left_manifest["source_variant"][field]
                != right_manifest["source_variant"][field]
            )
            if not changed:
                raise ValueError("same semantic form contains an unclassified source alias")
            category = "+".join(changed)
            left_sass = sass_by_implementation[left_id]
            right_sass = sass_by_implementation[right_id]
            same_operation = left_sass["operations"] == right_sass["operations"]
            same_encoding = left_sass["encodings"] == right_sass["encodings"]
            total["pair_count"] += 1
            total["same_operation_count"] += same_operation
            total["same_encoding_count"] += same_encoding
            category_counts[category]["pair_count"] += 1
            category_counts[category]["same_operation_count"] += same_operation
            category_counts[category]["same_encoding_count"] += same_encoding
    return {
        **dict(total),
        "categories": [
            {"category": category, **dict(counts)}
            for category, counts in sorted(category_counts.items())
        ],
    }


def analyze_modifier_encoding_bits(
    attribution_path: Path,
    manifest_by_implementation: dict[str, dict],
) -> dict:
    records = []
    for attribution in read_jsonl(attribution_path):
        if attribution["optimization"] != "O3":
            continue
        manifest = manifest_by_implementation[attribution["source_implementation_id"]]
        if manifest["context_profile_label"] != "runtime_zero":
            continue
        semantic = manifest["semantic_form"]
        source = manifest["source_variant"]
        for occurrence in attribution["occurrences"]:
            step = semantic["collector_steps"][occurrence["occurrence_index"]]
            sass = occurrence["sass_target"]
            records.append(
                {
                    "witness_id": (
                        f"{attribution['case_label']}:O3:"
                        f"{occurrence['occurrence_index']}"
                    ),
                    "case_label": attribution["case_label"],
                    "source_implementation_id": attribution[
                        "source_implementation_id"
                    ],
                    "occurrence_index": occurrence["occurrence_index"],
                    "ptx_instruction": occurrence["ptx_instruction"],
                    "features": {
                        "variant": semantic["variant"],
                        "weight_stationary": ".ws" in semantic["variant"],
                        "sparse": ".sp" in semantic["variant"],
                        "cta_group": semantic["cta_group"],
                        "kind": semantic["kind"],
                        "a_form": semantic["a_form"],
                        "scale_vector_semantics": semantic["scale_vector_semantics"],
                        "zero_column_mask": semantic["zero_column_mask"],
                        "step_count": len(semantic["collector_steps"]),
                        "occurrence_index": occurrence["occurrence_index"],
                        "collector_op": step["collector_op"],
                        "collector_buffer": step["collector_buffer"],
                        "ashift": step["ashift"],
                        "collector_spelling": source["collector_spelling"],
                        "scale_vector_spelling": source["scale_vector_spelling"],
                    },
                    "operation": sass["operation"],
                    "encoding": tuple(int(word, 16) for word in sass["encoding_words"]),
                }
            )

    def isolate(
        dimension: str,
        left_value,
        right_value,
        token: str,
        ignored_keys: set[str],
        change_label: str,
    ) -> dict:
        groups = defaultdict(lambda: defaultdict(list))
        for record in records:
            features = record["features"]
            key = tuple(
                (field, stable_value(value))
                for field, value in sorted(features.items())
                if field != dimension and field not in ignored_keys
            )
            groups[key][stable_value(features[dimension])].append(record)
        left_key = stable_value(left_value)
        right_key = stable_value(right_value)
        masks = Counter()
        direction_masks = Counter()
        candidate_pair_count = 0
        isolated_pair_count = 0
        witness_group_count = 0
        representative_witnesses = []
        for variants in groups.values():
            group_witnesses = []
            for left in variants.get(left_key, ()):
                for right in variants.get(right_key, ()):
                    candidate_pair_count += 1
                    if left["operation"].replace(token, "") != right["operation"].replace(token, ""):
                        continue
                    isolated_pair_count += 1
                    xor_mask = tuple(a ^ b for a, b in zip(left["encoding"], right["encoding"], strict=True))
                    set_mask = tuple((~a) & b & ((1 << 64) - 1) for a, b in zip(left["encoding"], right["encoding"], strict=True))
                    clear_mask = tuple(a & (~b) & ((1 << 64) - 1) for a, b in zip(left["encoding"], right["encoding"], strict=True))
                    masks[xor_mask] += 1
                    direction_masks[(set_mask, clear_mask)] += 1
                    group_witnesses.append((left, right, xor_mask, set_mask, clear_mask))
            if group_witnesses:
                witness_group_count += 1
                left, right, xor_mask, set_mask, clear_mask = group_witnesses[0]
                representative_witnesses.append(
                    {
                        "left_witness_id": left["witness_id"],
                        "right_witness_id": right["witness_id"],
                        "left_ptx_instruction": left["ptx_instruction"],
                        "right_ptx_instruction": right["ptx_instruction"],
                        "left_operation": left["operation"],
                        "right_operation": right["operation"],
                        "left_encoding_words": [f"0x{word:016x}" for word in left["encoding"]],
                        "right_encoding_words": [f"0x{word:016x}" for word in right["encoding"]],
                        "xor_mask": [f"0x{word:016x}" for word in xor_mask],
                        "set_mask": [f"0x{word:016x}" for word in set_mask],
                        "clear_mask": [f"0x{word:016x}" for word in clear_mask],
                    }
                )
        return {
            "dimension": dimension,
            "left_value": left_value,
            "right_value": right_value,
            "sass_token": token,
            "change_label": change_label,
            "candidate_pair_count": candidate_pair_count,
            "isolated_pair_count": isolated_pair_count,
            "witness_group_count": witness_group_count,
            "representative_witness_count": len(representative_witnesses),
            "representative_witnesses": representative_witnesses,
            "xor_masks": [
                {
                    "encoding_words": [f"0x{word:016x}" for word in mask],
                    "pair_count": count,
                }
                for mask, count in masks.most_common()
            ],
            "direction_masks": [
                {
                    "set_words": [f"0x{word:016x}" for word in set_mask],
                    "clear_words": [f"0x{word:016x}" for word in clear_mask],
                    "pair_count": count,
                }
                for (set_mask, clear_mask), count in direction_masks.most_common()
            ],
        }

    def isolate_token(
        token: str,
        ignored_keys: set[str],
        change_label: str,
        eligible=lambda features: True,
    ) -> dict:
        groups = defaultdict(lambda: defaultdict(list))
        for record in records:
            features = record["features"]
            if not eligible(features):
                continue
            key = (
                tuple(
                    (field, stable_value(value))
                    for field, value in sorted(features.items())
                    if field not in ignored_keys
                ),
                record["operation"].replace(token, ""),
            )
            groups[key][token in record["operation"]].append(record)
        masks = Counter()
        direction_masks = Counter()
        pair_count = 0
        witness_group_count = 0
        representative_witnesses = []
        for variants in groups.values():
            group_witnesses = []
            for left in variants[False]:
                for right in variants[True]:
                    pair_count += 1
                    xor_mask = tuple(a ^ b for a, b in zip(left["encoding"], right["encoding"], strict=True))
                    set_mask = tuple((~a) & b & ((1 << 64) - 1) for a, b in zip(left["encoding"], right["encoding"], strict=True))
                    clear_mask = tuple(a & (~b) & ((1 << 64) - 1) for a, b in zip(left["encoding"], right["encoding"], strict=True))
                    masks[xor_mask] += 1
                    direction_masks[(set_mask, clear_mask)] += 1
                    group_witnesses.append((left, right, xor_mask, set_mask, clear_mask))
            if group_witnesses:
                witness_group_count += 1
                left, right, xor_mask, set_mask, clear_mask = group_witnesses[0]
                representative_witnesses.append(
                    {
                        "left_witness_id": left["witness_id"],
                        "right_witness_id": right["witness_id"],
                        "left_ptx_instruction": left["ptx_instruction"],
                        "right_ptx_instruction": right["ptx_instruction"],
                        "left_operation": left["operation"],
                        "right_operation": right["operation"],
                        "left_encoding_words": [f"0x{word:016x}" for word in left["encoding"]],
                        "right_encoding_words": [f"0x{word:016x}" for word in right["encoding"]],
                        "xor_mask": [f"0x{word:016x}" for word in xor_mask],
                        "set_mask": [f"0x{word:016x}" for word in set_mask],
                        "clear_mask": [f"0x{word:016x}" for word in clear_mask],
                    }
                )
        return {
            "dimension": token.removeprefix("."),
            "left_value": False,
            "right_value": True,
            "sass_token": token,
            "change_label": change_label,
            "candidate_pair_count": pair_count,
            "isolated_pair_count": pair_count,
            "witness_group_count": witness_group_count,
            "representative_witness_count": len(representative_witnesses),
            "representative_witnesses": representative_witnesses,
            "xor_masks": [
                {
                    "encoding_words": [f"0x{word:016x}" for word in mask],
                    "pair_count": count,
                }
                for mask, count in masks.most_common()
            ],
            "direction_masks": [
                {
                    "set_words": [f"0x{word:016x}" for word in set_mask],
                    "clear_words": [f"0x{word:016x}" for word in clear_mask],
                    "pair_count": count,
                }
                for (set_mask, clear_mask), count in direction_masks.most_common()
            ],
        }

    spelling_keys = {"collector_spelling", "scale_vector_spelling"}

    return {
        "method": "paired O3 runtime_zero occurrences with identical concrete SASS after removing only the tested modifier token",
        "rules": [
            isolate("cta_group", 1, 2, ".2CTA", set(), ".cta_group::1 → .cta_group::2"),
            isolate(
                "ashift",
                False,
                True,
                ".ASHIFT",
                spelling_keys,
                "无 .ashift → .ashift",
            ),
            isolate_token(".A_KEEP", {"collector_op", "occurrence_index", "step_count"} | spelling_keys, "A discard → fill/keep"),
            isolate_token(".B_KEEP", {"collector_op", "occurrence_index", "step_count"} | spelling_keys, "B discard/lastuse → fill/use"),
            isolate_token(".BUFFER1", {"collector_buffer"} | spelling_keys, "B0 → B1"),
            isolate_token(".BUFFER2", {"collector_buffer"} | spelling_keys, "B0 → B2"),
            isolate_token(".BUFFER3", {"collector_buffer"} | spelling_keys, "B0 → B3"),
            isolate_token(".4X", {"scale_vector_semantics"} | spelling_keys, "非 4X → 4X"),
            isolate_token(
                ".WS",
                {"variant", "weight_stationary", "collector_buffer"} | spelling_keys,
                "非 WS → WS",
                lambda features: (
                    features["collector_op"] == "discard"
                    and not features["zero_column_mask"]
                    and features["scale_vector_semantics"] is None
                    and features["cta_group"] == 1
                ),
            ),
        ],
    }


def percent(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator} ({numerator / denominator:.1%})"


def outcome_counts(rows: list[dict]) -> dict:
    return dict(sorted(Counter(row["outcome"] for row in rows).items()))


def write_predictor_table(lines: list[str], groups: list[dict], keys: tuple[str, ...]):
    lines.append("| " + " | ".join((*keys, "结果与数量")) + " |")
    lines.append("|" + "---|" * (len(keys) + 1))
    for group in groups:
        values = [f"`{display_value(group['values'][key])}`" for key in keys]
        outcomes = "；".join(f"`{label}` {count}" for label, count in group["outcomes"].items())
        lines.append("| " + " | ".join((*values, outcomes)) + " |")


def write_markdown(path: Path, report: dict) -> None:
    guard = report["guard"]
    issuer = report["issuer"]
    aliases = report["aliases"]
    encoding_bits = report["encoding_bits"]
    inverse = report["inverse"]
    lines = [
        "# `tcgen05.mma` 可预测映射与逆向可恢复性规则",
        "",
        "> 本页由 `analyze_mapping_rules.py` 从 expanded manifest、O3 核心 SASS attribution 和逐配对 context differences 自动生成。结论只适用于当前 PTX 9.0、`sm_110a`、生成矩阵和工具链。",
        "",
        f"> 当前输入与工具链已写入生成 JSON：ptxas SHA-256 `{report['toolchain']['ptxas_sha256']}`，nvdisasm SHA-256 `{report['toolchain']['nvdisasm_sha256']}`。",
        "",
        "## guard lowering 的精确分类",
        "",
        f"正 guard 的 1,152 个单因素设计分为：{', '.join(f'`{key}` {value}' for key, value in guard['outcome_counts'].items())}。正负极性分类不一致的设计数为 {guard['polarity_mismatch_count']}。",
        "",
        f"在当前字段集中，能无误差预测两种路径的最小特征组合大小为 {guard['minimal_predictor_size']}，第一组最小预测器是 `{' + '.join(guard['selected_predictor'])}`。精确规则可以写成：",
        "",
        "```text",
        "first_occurrence_core_predication =",
        "    step_count == 2",
        "    and (",
        "        variant in {mma.sp, mma.ws.sp}",
        "        or (kind in {f16, tf32, f8f6f4, i8} and zero_column_mask == false)",
        "    )",
        "",
        "其余合法形态 = external_control_flow",
        "```",
        "",
        f"分析器已把这条手写公式逐项回放到 {guard['handwritten_formula_verification']['checked_design_count']} 个设计，mismatch={guard['handwritten_formula_verification']['mismatch_count']}；出现任何 mismatch 会使规则挖掘失败。",
        "",
        "352 个 `first_occurrence_core_predication` 样本的 occurrence 谓词形状全部是 `(true, false)`：只有 collector 序列第一条核心 MMA 带 `@UPn/@!UPn`，第二条不重复携带 guard。其余 800 个设计的所有核心 occurrence 都不带 guard，由外围控制流实现条件执行。正负 guard 只改变谓词极性，不改变上述路径分类。完整预测分组保存在[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)中。",
        "",
    ]
    lines.extend(
        [
            "## lane-0 issuer 的核心重编号条件",
            "",
            f"lane-0 issuer 的 1,152 个单因素设计分为：{', '.join(f'`{key}` {value}' for key, value in issuer['outcome_counts'].items())}。",
            "",
            f"在当前字段集中，能无误差预测 `renumber_only` 与 `stable_layout` 的最小特征组合大小为 {issuer['minimal_predictor_size']}，第一组最小预测器是 `{' + '.join(issuer['selected_predictor'])}`。精确规则可以写成：",
            "",
            "```text",
            "renumber_only =",
            "    a_form == tmem_address",
            "    and (",
            "        (variant == mma.sp and kind in {mxf4, mxf4nvf4, mxf8f6f4})",
            "        or (variant == mma.ws.sp and zero_column_mask == true)",
            "    )",
            "",
            "其余合法形态 = stable_layout",
            "```",
            "",
            f"分析器已把这条手写公式逐项回放到 {issuer['handwritten_formula_verification']['checked_design_count']} 个设计，mismatch={issuer['handwritten_formula_verification']['mismatch_count']}；出现任何 mismatch 会使规则挖掘失败。",
            "",
            "前一分支有 100 个设计，后一分支有 68 个设计，合计 168 个；它们在 O1–O3 仅改变具体寄存器编号，不改变寄存器类别、别名关系、核心助记符或规范操作。完整预测分组保存在[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)中。",
            "",
        ]
    )
    lines.extend(
        [
            "",
            "这里的预测目标只是在 O3 核心 MMA 上是否发生纯物理寄存器重编号；lane-0 issuer 对所有设计的完整控制流和活跃寄存器仍有影响。",
            "",
            "## PTX source alias 的编码等价性",
            "",
            f"在同一 semantic form 内比较 O3 `runtime_zero` 的 source spelling，共有 {aliases['pair_count']} 对。{aliases['same_operation_count']}/{aliases['pair_count']} 对生成完全相同的具体核心 SASS 操作文本，{aliases['same_encoding_count']}/{aliases['pair_count']} 对连两个 64-bit encoding word 也完全相同。",
            "",
            "| 仅改变的 source spelling | 配对数 | 核心操作文本相同 | 核心编码相同 |",
            "|---|---:|---:|---:|",
        ]
    )
    for category in aliases["categories"]:
        lines.append(f"| `{category['category']}` | {category['pair_count']} | {category['same_operation_count']} | {category['same_encoding_count']} |")
    lines.extend(
        [
            "",
            "因此，显式 `.collector::*::discard` 与缺省 discard、缺省 scale-vector 与其等价显式拼写，在当前语义条件相同的配对中都是机器编码级 alias。仅凭核心 SASS 或核心机器码不能恢复用户采用了哪一种等价 PTX 拼写。",
            "",
            "## 已隔离的核心机器编码位",
            "",
            "下表只保留具体寄存器文本完全相同、移除被测 SASS modifier 后整条操作文本也完全相同的 O3 单因素配对，因此 XOR mask 不混入寄存器编号变化。`word 0/1` 按 `nvdisasm` 在 attribution 中输出的两个 64-bit encoding word 顺序编号。",
            "",
            "| PTX/SASS 变化 | 独立 witness 组 | 候选配对 | word 0 XOR | word 1 XOR | 位方向 |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for rule in encoding_bits["rules"]:
        if len(rule["xor_masks"]) == 1:
            mask = rule["xor_masks"][0]
            directions = rule["direction_masks"]
            if len(directions) == 1:
                direction = directions[0]
                set_nonzero = any(int(word, 16) for word in direction["set_words"])
                clear_nonzero = any(int(word, 16) for word in direction["clear_words"])
                direction_label = "置位" if set_nonzero and not clear_nonzero else "清位" if clear_nonzero and not set_nonzero else "混合"
            else:
                direction_label = "多方向"
            lines.append(f"| `{rule['change_label']}` / `{rule['sass_token']}` | {rule['witness_group_count']} | {rule['isolated_pair_count']} | `{mask['encoding_words'][0]}` | `{mask['encoding_words'][1]}` | {direction_label} |")
        else:
            lines.append(f"| `{rule['change_label']}` / `{rule['sass_token']}` | {rule['witness_group_count']} | {rule['isolated_pair_count']} | — | — | 多 mask |")
    lines.extend(
        [
            "",
            "候选配对会因等价 source spelling 和同组重复实例形成笛卡尔积，因此表中把独立 witness 组作为证据规模，把候选配对仅作为一致性重复数；每组的 witness ID、左右 PTX、SASS、encoding、置位 mask 和清位 mask 均保存在生成 JSON。所有行都只有一个稳定 XOR mask，其中 `.4X` 是清位，其余当前字段是置位或表中注明的方向；B buffer 的 `B0/B1/B2/B3` 对应 word 1 的两位字段 `0x0000/0x8000/0x10000/0x18000`。这里描述的是当前 Thor 工具链输出，不把 bit 编号外推到其他架构；`A/B_REUSE` 配对还会改变高位调度控制字段，尚未列入已隔离规则。",
            "",
            "## 从核心 SASS 反推 PTX 字段",
            "",
            f"分析集合为 O3 `runtime_zero` 的 {inverse['occurrence_count']} 个目标 occurrence，共有 {inverse['unique_ptx_instruction_count']} 种 PTX 目标指令文本和 {inverse['sass_signature_count']} 种去除具体寄存器编号后的核心 SASS signature。出现多 PTX 拼写或字段歧义的 signature 有 {inverse['collision_signature_count']} 个，其中存在语义字段歧义的有 {inverse['semantic_collision_signature_count']} 个。",
            "",
            "| PTX 字段 | 可唯一恢复的 SASS signature | 加权 occurrence | 当前结论 |",
            "|---|---:|---:|---|",
        ]
    )
    for field in inverse["field_recoverability"]:
        signature_ratio = percent(field["unambiguous_signature_count"], field["signature_count"])
        occurrence_ratio = percent(field["unambiguous_occurrence_count"], field["occurrence_count"])
        if field["unambiguous_signature_count"] == field["signature_count"]:
            conclusion = "样本内可由核心 SASS 唯一恢复"
        elif field["unambiguous_signature_count"] == 0:
            conclusion = "核心 SASS signature 无法唯一恢复"
        else:
            conclusion = "条件可恢复，存在多对一组"
        lines.append(f"| `{field['field']}` | {signature_ratio} | {occurrence_ratio} | {conclusion} |")
    lines.extend(
        [
            "",
            "“样本内可恢复”只表示当前生成集合中没有碰撞；它不是 ISA 对未来形态的一一对应保证。source spelling 字段尤其容易在规范化或优化后丢失。",
            "",
            "## 主要多对一实例",
            "",
        ]
    )
    for index, collision in enumerate(inverse["top_collision_groups"][:6], start=1):
        fields = "；".join(
            f"`{field}`={','.join(values)}" for field, values in collision["ambiguous_fields"].items()
        ) or "仅 PTX 拼写不同"
        lines.extend(
            [
                f"### {index}. `{collision['sass_signature']}`",
                "",
                f"该 signature 汇合 {collision['ptx_spelling_count']} 种 PTX 目标拼写、{collision['occurrence_count']} 个 occurrence；歧义字段：{fields}。",
                "",
            ]
        )
        for spelling in collision["ptx_spellings"][:4]:
            lines.append(f"- `{spelling}`")
        if len(collision["ptx_spellings"]) > 4:
            lines.append(f"- 其余 {len(collision['ptx_spellings']) - 4} 种拼写省略；完整集合见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)。")
        lines.append("")
    lines.extend(
        [
            "## 规则使用边界",
            "",
            "- guard 与 issuer 的分类规则来自当前有限字段集合；加入 descriptor 常量、真实非恒等 producer 或其他工具链版本后必须重新运行分析器。",
            "- 核心 SASS 的可恢复性不包含外围指令。某些 source/context 信息虽然不在核心中，仍可能从完整 kernel 恢复。",
            "- 逆向 signature 分析会规范化具体寄存器编号，因此不能用该小节预测物理寄存器分配；上一节的机器编码位结论使用的是未规范化且寄存器文本完全相同的严格 witness，不受此限制。",
            "- descriptor 的动态内容尚未枚举，因此 `idesc`、SMEM descriptor 的形状、类型、布局、stride 和 swizzle 位型仍属于未解决层。",
            "",
            "## 证据入口",
            "",
            "- 规则挖掘器：[`../../analyze_mapping_rules.py`](../../analyze_mapping_rules.py)",
            "- 完整机器可读结果：[`../../results/rule-mining/mapping_rule_analysis.json`](../../results/rule-mining/mapping_rule_analysis.json)",
            "- 生成 manifest：[`../../results/expanded/sources/manifest.jsonl`](../../results/expanded/sources/manifest.jsonl)",
            "- 核心 SASS attribution：[`../../results/expanded/sass/sass_attribution.jsonl`](../../results/expanded/sass/sass_attribution.jsonl)",
            "- 上下文统计：[`../tcgen05_mma_上下文差分报告.md`](../tcgen05_mma_上下文差分报告.md)",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--attribution", type=Path, required=True)
    parser.add_argument("--differences", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report-output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = reset_owned_directory(
        args.output_dir,
        owner="thor_tcgen05_mapping_rule_mining",
        protected=(ROOT,),
    )
    manifests = list(read_jsonl(args.manifest))
    manifest_by_implementation = {
        row["source_implementation_id"]: row for row in manifests
    }
    if len(manifest_by_implementation) != len(manifests):
        raise ValueError("duplicate source implementation IDs in manifest")
    guard_rows, issuer_rows, context_checks = classify_context_rules(
        args.differences, manifest_by_implementation
    )
    guard_predictors = minimal_exact_predictors(guard_rows)
    issuer_predictors = minimal_exact_predictors(issuer_rows)
    if not guard_predictors or not issuer_predictors:
        raise ValueError("no exact predictor found within configured feature limit")
    guard_selected = guard_predictors[0]
    issuer_selected = issuer_predictors[0]
    if any(row["outcome"] == "unexpected_guard_shape" for row in guard_rows):
        raise ValueError("encountered an unsupported guard predicate shape")
    guard_formula_mismatches = [
        row for row in guard_rows
        if row["outcome"] != expected_guard_outcome(row["features"])
    ]
    issuer_formula_mismatches = [
        row for row in issuer_rows
        if row["outcome"] != expected_issuer_outcome(row["features"])
    ]
    if guard_formula_mismatches or issuer_formula_mismatches:
        raise ValueError(
            "handwritten rule formula no longer matches mined outcomes: "
            f"guard={len(guard_formula_mismatches)}, "
            f"issuer={len(issuer_formula_mismatches)}"
        )
    aliases = analyze_source_aliases(args.attribution, manifest_by_implementation)
    if aliases["same_encoding_count"] != aliases["pair_count"]:
        raise ValueError("a source alias pair changed core encoding")
    encoding_bits = analyze_modifier_encoding_bits(args.attribution, manifest_by_implementation)
    for rule in encoding_bits["rules"]:
        if rule["isolated_pair_count"] == 0 or len(rule["xor_masks"]) != 1:
            raise ValueError(f"modifier field is not uniquely isolated: {rule['change_label']}")
    sass_report_path = args.attribution.parent / "sass_report.json"
    compile_report_path = args.attribution.parent.parent / "compile_report.json"
    sass_report = json.loads(sass_report_path.read_text(encoding="utf-8")) if sass_report_path.is_file() else {}
    compile_report = json.loads(compile_report_path.read_text(encoding="utf-8")) if compile_report_path.is_file() else {}
    report = {
        "schema_version": "thor_tcgen05_mapping_rule_mining_v2",
        "status": "COMPLETE",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "manifest": {"path": str(args.manifest), "sha256": sha256_file(args.manifest)},
            "attribution": {"path": str(args.attribution), "sha256": sha256_file(args.attribution)},
            "differences": {"path": str(args.differences), "sha256": sha256_file(args.differences)},
        },
        "toolchain": {
            "ptxas_sha256": compile_report.get("ptxas_sha256"),
            "ptxas_version": compile_report.get("ptxas_version"),
            "nvdisasm_sha256": sass_report.get("nvdisasm_sha256"),
            "nvdisasm_version": sass_report.get("nvdisasm_version"),
        },
        "guard": {
            "design_count": len(guard_rows),
            "outcome_counts": outcome_counts(guard_rows),
            "polarity_mismatch_count": len(context_checks["polarity_mismatches"]),
            "guard_shape_counts": {
                display_value(shape): count
                for shape, count in sorted(
                    Counter(row["guard_shape"] for row in guard_rows).items(),
                    key=lambda item: stable_value(item[0]),
                )
            },
            "minimal_predictor_size": len(guard_selected),
            "minimal_predictors": [list(keys) for keys in guard_predictors],
            "selected_predictor": list(guard_selected),
            "selected_predictor_groups": predictor_groups(guard_rows, guard_selected),
            "handwritten_formula_verification": {
                "checked_design_count": len(guard_rows),
                "mismatch_count": len(guard_formula_mismatches),
                "status": "PASS",
            },
        },
        "issuer": {
            "design_count": len(issuer_rows),
            "outcome_counts": outcome_counts(issuer_rows),
            "minimal_predictor_size": len(issuer_selected),
            "minimal_predictors": [list(keys) for keys in issuer_predictors],
            "selected_predictor": list(issuer_selected),
            "selected_predictor_groups": predictor_groups(issuer_rows, issuer_selected),
            "handwritten_formula_verification": {
                "checked_design_count": len(issuer_rows),
                "mismatch_count": len(issuer_formula_mismatches),
                "status": "PASS",
            },
        },
        "aliases": aliases,
        "encoding_bits": encoding_bits,
        "inverse": analyze_inverse_mapping(args.attribution, manifest_by_implementation),
    }
    json_path = output_dir / "mapping_rule_analysis.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = output_dir / "mapping_rule_analysis.md"
    write_markdown(markdown_path, report)
    if args.report_output is not None:
        write_markdown(args.report_output, report)
    print(
        f"guard={report['guard']['outcome_counts']} "
        f"issuer={report['issuer']['outcome_counts']} "
        f"inverse_signatures={report['inverse']['sass_signature_count']} "
        f"status={report['status']}"
    )


if __name__ == "__main__":
    main()

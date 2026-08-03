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
REGISTER_RE = re.compile(r"\b(UR|UP|R|P)(\d+)\b")
BLOCK_SCALE_KINDS = {"mxf8f6f4", "mxf4", "mxf4nvf4"}
PREDICATE_PRESSURE_PROFILES = tuple(
    f"predicate_pressure_{index}" for index in range(1, 7)
)


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


EXTENDED_BRANCH_ISSUER_PROFILES = (
    "lane0_issuer",
    "lane31_issuer",
    "dynamic_lane_issuer",
    "thread0_issuer",
)
EXTENDED_PRODUCER_PROFILES = (
    "derived_producers",
    "nonidentity_producers",
    "branched_producers",
    "global_load_producers",
)


def expected_global_load_outcome(features: dict) -> str:
    renumber_only = (
        features["variant"] == "mma.sp"
        and (
            features["a_form"] == "tmem_address"
            or features["kind"] in BLOCK_SCALE_KINDS
        )
    ) or (
        features["variant"] == "mma.ws.sp"
        and (
            features["a_form"] == "tmem_address"
            or features["zero_column_mask"]
        )
    )
    return "renumber_only" if renumber_only else "stable_layout"


def analyze_extended_context_rules(
    differences_path: Path,
    manifest_by_implementation: dict[str, dict],
) -> dict:
    rows_by_profile = defaultdict(list)
    for row in read_jsonl(differences_path):
        if row["optimization"] != "O3":
            continue
        profile = row["treatment_profile"]
        if profile not in set(EXTENDED_BRANCH_ISSUER_PROFILES) | set(EXTENDED_PRODUCER_PROFILES) | {"compound_predicated_issuer"}:
            continue
        manifest = manifest_by_implementation[row["treatment_case"]["source_implementation_id"]]
        features = case_features(manifest)
        if profile == "compound_predicated_issuer":
            operations = [
                occurrence["treatment"]["sass"]["operation"]
                for occurrence in row["core"]["occurrences"]
            ]
            predicate_shape = tuple(bool(DIRECT_GUARD_RE.match(operation)) for operation in operations)
            outcome = (
                "first_occurrence_core_predication"
                if predicate_shape == (True, False)
                else "external_control_flow"
                if not any(predicate_shape)
                else "unexpected_predicate_shape"
            )
        else:
            predicate_shape = None
            outcome = "renumber_only" if row["core"]["renumber_only"] else "stable_layout"
        rows_by_profile[profile].append(
            {
                "features": features,
                "outcome": outcome,
                "predicate_shape": predicate_shape,
                "core_mnemonic_changed": row["core"]["mnemonic_changed"],
                "core_normalized_operation_changed": row["core"]["normalized_operation_changed"],
                "kernel_normalized_sequence_changed": row["kernel"]["normalized_sequence_changed"],
                "kernel_instruction_count_changed": row["kernel"]["instruction_count_delta"] != 0,
                "kernel_peak_live_registers_changed": row["kernel"]["peak_live_registers_changed"],
            }
        )

    required_profiles = set(EXTENDED_BRANCH_ISSUER_PROFILES) | set(EXTENDED_PRODUCER_PROFILES) | {"compound_predicated_issuer"}
    missing_profiles = sorted(required_profiles - set(rows_by_profile))
    profile_results = {}
    formula_mismatches = []
    for profile, rows in sorted(rows_by_profile.items()):
        result = {
            "design_count": len(rows),
            "outcome_counts": outcome_counts(rows),
            "core_mnemonic_changed_count": sum(row["core_mnemonic_changed"] for row in rows),
            "core_normalized_operation_changed_count": sum(row["core_normalized_operation_changed"] for row in rows),
            "kernel_normalized_sequence_changed_count": sum(row["kernel_normalized_sequence_changed"] for row in rows),
            "kernel_instruction_count_changed_count": sum(row["kernel_instruction_count_changed"] for row in rows),
            "kernel_peak_live_registers_changed_count": sum(row["kernel_peak_live_registers_changed"] for row in rows),
        }
        if profile in EXTENDED_BRANCH_ISSUER_PROFILES:
            mismatches = [row for row in rows if row["outcome"] != expected_issuer_outcome(row["features"])]
            result["formula"] = "same renumber_only condition as lane0_issuer"
        elif profile == "compound_predicated_issuer":
            mismatches = [
                row
                for row in rows
                if row["outcome"]
                != (
                    "first_occurrence_core_predication"
                    if row["features"]["step_count"] == 2
                    else "external_control_flow"
                )
            ]
            result["formula"] = "step_count == 2 -> first occurrence predicated; otherwise external control flow"
            result["predicate_shape_counts"] = {
                display_value(shape): count
                for shape, count in sorted(
                    Counter(row["predicate_shape"] for row in rows).items(),
                    key=lambda item: stable_value(item[0]),
                )
            }
        elif profile == "global_load_producers":
            mismatches = [row for row in rows if row["outcome"] != expected_global_load_outcome(row["features"])]
            result["formula"] = "mma.sp: tmem A or block-scale kind; mma.ws.sp: tmem A or zero-column-mask"
        elif profile in {"nonidentity_producers", "branched_producers"}:
            mismatches = [row for row in rows if row["outcome"] != "renumber_only"]
            result["formula"] = "all generated designs -> renumber_only"
        else:
            mismatches = [row for row in rows if row["outcome"] != "stable_layout"]
            result["formula"] = "identity chain at O3 -> stable_layout"
        result["formula_verification"] = {
            "checked_design_count": len(rows),
            "mismatch_count": len(mismatches),
            "status": "PASS" if not mismatches else "FAIL",
        }
        formula_mismatches.extend((profile, row) for row in mismatches)
        profile_results[profile] = result

    branch_consistency_mismatches = []
    if not missing_profiles:
        branch_outcomes = defaultdict(dict)
        for profile in EXTENDED_BRANCH_ISSUER_PROFILES:
            for row in rows_by_profile[profile]:
                key = stable_value(row["features"])
                branch_outcomes[key][profile] = row["outcome"]
        branch_consistency_mismatches = [
            {"features": key, "outcomes": outcomes}
            for key, outcomes in branch_outcomes.items()
            if len(outcomes) != len(EXTENDED_BRANCH_ISSUER_PROFILES)
            or len(set(outcomes.values())) != 1
        ]
    return {
        "status": "COMPLETE" if not missing_profiles and not formula_mismatches and not branch_consistency_mismatches else "PENDING_NEW_RESULTS" if missing_profiles else "FAIL",
        "missing_profiles": missing_profiles,
        "profiles": profile_results,
        "branch_issuer_cross_profile_mismatch_count": len(branch_consistency_mismatches),
        "formula_mismatch_count": len(formula_mismatches),
    }


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
        if manifest["source_variant"]["collector_spelling"] == "encoding_enable_index_sweep":
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
        if manifest["source_variant"]["collector_spelling"] == "encoding_enable_index_sweep":
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
        if source["collector_spelling"] == "encoding_enable_index_sweep":
            continue
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


def encoding_delta(left: tuple[int, int], right: tuple[int, int]) -> dict:
    full_mask = (1 << 64) - 1
    xor_mask = tuple(a ^ b for a, b in zip(left, right, strict=True))
    set_mask = tuple((~a) & b & full_mask for a, b in zip(left, right, strict=True))
    clear_mask = tuple(a & (~b) & full_mask for a, b in zip(left, right, strict=True))
    return {"xor": xor_mask, "set": set_mask, "clear": clear_mask}


def summarize_encoding_deltas(deltas: list[dict]) -> dict:
    if not deltas:
        return {
            "pair_count": 0,
            "xor_masks": [],
            "direction_masks": [],
            "stable_set_words": ["0x0000000000000000"] * 2,
            "stable_clear_words": ["0x0000000000000000"] * 2,
            "variable_words": ["0x0000000000000000"] * 2,
        }
    xor_counts = Counter(delta["xor"] for delta in deltas)
    direction_counts = Counter(
        (delta["set"], delta["clear"]) for delta in deltas
    )
    stable_set = tuple(
        bits
        for bits in (
            (1 << 64) - 1,
            (1 << 64) - 1,
        )
    )
    stable_clear = stable_set
    union_xor = (0, 0)
    for delta in deltas:
        stable_set = tuple(a & b for a, b in zip(stable_set, delta["set"], strict=True))
        stable_clear = tuple(a & b for a, b in zip(stable_clear, delta["clear"], strict=True))
        union_xor = tuple(a | b for a, b in zip(union_xor, delta["xor"], strict=True))
    stable = tuple(a | b for a, b in zip(stable_set, stable_clear, strict=True))
    variable = tuple(a & ~b for a, b in zip(union_xor, stable, strict=True))
    return {
        "pair_count": len(deltas),
        "xor_masks": [
            {
                "encoding_words": [f"0x{word:016x}" for word in mask],
                "pair_count": count,
            }
            for mask, count in xor_counts.most_common()
        ],
        "direction_masks": [
            {
                "set_words": [f"0x{word:016x}" for word in set_mask],
                "clear_words": [f"0x{word:016x}" for word in clear_mask],
                "pair_count": count,
            }
            for (set_mask, clear_mask), count in direction_counts.most_common()
        ],
        "stable_set_words": [f"0x{word:016x}" for word in stable_set],
        "stable_clear_words": [f"0x{word:016x}" for word in stable_clear],
        "variable_words": [f"0x{word:016x}" for word in variable],
    }


def operation_parts(operation: str) -> tuple[str | None, str, list[str]]:
    predicate_match = re.match(r"^(@!?(?:UP\d+|P\d+|UPT|PT))\s+", operation)
    predicate = predicate_match.group(1) if predicate_match else None
    body = operation[predicate_match.end():] if predicate_match else operation
    mnemonic, operand_text = body.split(" ", 1)
    return predicate, mnemonic, [item.strip() for item in operand_text.split(",")]


def semantic_encoding_payload(encoding: tuple[int, int]) -> tuple[int, int]:
    """Keep opcode/modifier/predicate fields while removing physical UR slots and scheduling."""

    word0_register_mask = sum(0xFF << shift for shift in (24, 32, 40, 48))
    word0 = encoding[0] & (~word0_register_mask & ((1 << 64) - 1))
    word1 = encoding[1] & 0x0000000007FFFF00
    return word0, word1


def analyze_opcode_layout(runtime_records: list[dict]) -> dict:
    rows = Counter()
    for record in runtime_records:
        semantic = record["manifest"]["semantic_form"]
        _, mnemonic, _ = operation_parts(record["operation"])
        word0, word1 = record["encoding"]
        rows[
            (
                mnemonic.split(".", 1)[0],
                semantic["a_form"],
                semantic["kind"],
                semantic["variant"],
                f"0x{(word0 >> 56) & 0xFF:02x}",
                f"0x{word0 & 0xFFF:03x}",
                f"0x{word1 & 0x300:03x}",
            )
        ] += 1
    return {
        "field_model": {
            "word0_high_opcode_bits": "word 0 [63:56] (includes the .4X direction bit at bit 62)",
            "word0_low_opcode_bits": "word 0 [11:0]",
            "word1_kind_bits": "word 1 [9:8]",
            "word0_guard_index_bits": "word 0 [14:12]",
            "word0_guard_negate_bit": "word 0 [15]",
        },
        "observed_rows": [
            {
                "sass_family": key[0],
                "a_form": key[1],
                "kind": key[2],
                "variant": key[3],
                "word0_high_byte": key[4],
                "word0_low_12": key[5],
                "word1_kind_field": key[6],
                "occurrence_count": count,
            }
            for key, count in sorted(rows.items())
        ],
    }


def analyze_scheduling_control(all_occurrences: list[dict]) -> dict:
    mask = 0xFFFFFFFFF8000000
    by_optimization = defaultdict(Counter)
    values = []
    for record in all_occurrences:
        if record["context_profile"] != "runtime_zero":
            continue
        value = record["encoding"][1] & mask
        values.append(value)
        by_optimization[record["optimization"]][value] += 1
    variable_mask = 0
    if values:
        reference = values[0]
        for value in values[1:]:
            variable_mask |= reference ^ value
    return {
        "word": 1,
        "mask": f"0x{mask:016x}",
        "semantic_payload_boundary": "bits [26:0] contain destination/kind/modifier/enable fields; bits [63:27] are treated as compiler scheduling/control",
        "observed_variable_mask": f"0x{variable_mask:016x}",
        "per_optimization": {
            optimization: {
                "distinct_value_count": len(counter),
                "top_values": [
                    {"value": f"0x{value:016x}", "occurrence_count": count}
                    for value, count in counter.most_common(16)
                ],
            }
            for optimization, counter in sorted(by_optimization.items())
        },
        "mapping_policy": "excluded from semantic opcode prediction and retained as an observed compiler-scheduling codebook",
    }


def analyze_sparse_encoding_aliases(runtime_records: list[dict]) -> dict:
    groups = defaultdict(lambda: defaultdict(list))
    for record in runtime_records:
        semantic = record["manifest"]["semantic_form"]
        variant = semantic["variant"]
        sparse = variant.endswith(".sp")
        base_variant = variant.removesuffix(".sp")
        step = semantic["collector_steps"][record["occurrence_index"]]
        key = (
            base_variant,
            semantic["cta_group"],
            semantic["kind"],
            semantic["a_form"],
            semantic["scale_vector_semantics"],
            semantic["zero_column_mask"],
            stable_value(step),
            normalize_operation(record["operation"]),
        )
        groups[key][sparse].append(record)
    witness_group_count = 0
    pair_count = 0
    same_payload_count = 0
    examples = []
    for variants in groups.values():
        if not variants[False] or not variants[True]:
            continue
        witness_group_count += 1
        for dense in variants[False]:
            for sparse in variants[True]:
                pair_count += 1
                same = semantic_encoding_payload(dense["encoding"]) == semantic_encoding_payload(sparse["encoding"])
                same_payload_count += same
                if len(examples) < 12:
                    examples.append(
                        {
                            "dense_operation": dense["operation"],
                            "sparse_operation": sparse["operation"],
                            "dense_payload": [
                                f"0x{word:016x}"
                                for word in semantic_encoding_payload(dense["encoding"])
                            ],
                            "sparse_payload": [
                                f"0x{word:016x}"
                                for word in semantic_encoding_payload(sparse["encoding"])
                            ],
                        }
                    )
    return {
        "method": "dense/sparse pairs with the same normalized core SASS signature; physical UR slots and scheduling bits removed",
        "witness_group_count": witness_group_count,
        "pair_count": pair_count,
        "same_semantic_payload_count": same_payload_count,
        "different_semantic_payload_count": pair_count - same_payload_count,
        "interpretation": ".sp has no independently recoverable core opcode bit in colliding signatures; metadata/operand contract is required",
        "examples": examples,
    }


def analyze_canonical_mapping(
    attribution_path: Path,
    manifest_by_implementation: dict[str, dict],
) -> dict:
    by_semantic_form = defaultdict(lambda: {"manifest": None, "keys": set()})
    inverse = defaultdict(set)
    for attribution in read_jsonl(attribution_path):
        if attribution["optimization"] != "O3":
            continue
        manifest = manifest_by_implementation[attribution["source_implementation_id"]]
        if manifest["context_profile_label"] != "runtime_zero":
            continue
        if manifest["source_variant"]["collector_spelling"] == "encoding_enable_index_sweep":
            continue
        semantic_form_id = manifest["semantic_form_id"]
        group = by_semantic_form[semantic_form_id]
        group["manifest"] = manifest
        sequence = []
        for occurrence in attribution["occurrences"]:
            sass = occurrence["sass_target"]
            encoding = tuple(int(word, 16) for word in sass["encoding_words"])
            payload = semantic_encoding_payload(encoding)
            sequence.append(
                (
                    normalize_operation(sass["operation"]),
                    f"0x{payload[0]:016x}",
                    f"0x{payload[1]:016x}",
                )
            )
        key = tuple(sequence)
        group["keys"].add(key)
        inverse[key].add(semantic_form_id)

    forward_rules = []
    for semantic_form_id, group in sorted(by_semantic_form.items()):
        if len(group["keys"]) != 1:
            raise ValueError(
                f"semantic form has multiple canonical O3 mappings: {semantic_form_id}"
            )
        key = next(iter(group["keys"]))
        forward_rules.append(
            {
                "semantic_form_id": semantic_form_id,
                "semantic_form": group["manifest"]["semantic_form"],
                "occurrences": [
                    {
                        "normalized_sass": item[0],
                        "semantic_payload_word0": item[1],
                        "semantic_payload_word1": item[2],
                    }
                    for item in key
                ],
            }
        )

    inverse_rules = []
    roundtrip_mismatch_count = 0
    for key, candidate_ids in sorted(inverse.items(), key=lambda item: item[0]):
        candidates = sorted(candidate_ids)
        inverse_rules.append(
            {
                "occurrences": [
                    {
                        "normalized_sass": item[0],
                        "semantic_payload_word0": item[1],
                        "semantic_payload_word1": item[2],
                    }
                    for item in key
                ],
                "candidate_semantic_form_ids": candidates,
                "candidate_count": len(candidates),
            }
        )
    for rule in forward_rules:
        key = tuple(
            (
                item["normalized_sass"],
                item["semantic_payload_word0"],
                item["semantic_payload_word1"],
            )
            for item in rule["occurrences"]
        )
        roundtrip_mismatch_count += int(
            rule["semantic_form_id"] not in inverse[key]
        )
    return {
        "optimization": "O3",
        "profile": "runtime_zero",
        "payload_masks": {
            "word0": "0xff00000000ffffff",
            "word1": "0x0000000007ffff00",
            "excluded": "physical UR slots, destination UR slot, and scheduling/control high bits",
        },
        "forward_rule_count": len(forward_rules),
        "inverse_rule_count": len(inverse_rules),
        "ambiguous_inverse_rule_count": sum(
            rule["candidate_count"] > 1 for rule in inverse_rules
        ),
        "candidate_count_distribution": {
            str(candidate_count): rule_count
            for candidate_count, rule_count in sorted(
                Counter(rule["candidate_count"] for rule in inverse_rules).items()
            )
        },
        "max_candidate_count": max(
            (rule["candidate_count"] for rule in inverse_rules), default=0
        ),
        "roundtrip_mismatch_count": roundtrip_mismatch_count,
        "forward_rules": forward_rules,
        "inverse_rules": inverse_rules,
    }


def analyze_extended_encoding(
    attribution_path: Path,
    differences_path: Path,
    manifest_by_implementation: dict[str, dict],
) -> dict:
    attribution_by_key = {}
    runtime_records = []
    all_occurrences = []
    for attribution in read_jsonl(attribution_path):
        attribution_by_key[(attribution["source_implementation_id"], attribution["optimization"])] = attribution
        manifest = manifest_by_implementation[attribution["source_implementation_id"]]
        for occurrence in attribution["occurrences"]:
            sass = occurrence["sass_target"]
            if sass is None:
                raise ValueError(f"missing SASS target in {attribution['case_label']}")
            record = {
                "manifest": manifest,
                "optimization": attribution["optimization"],
                "context_profile": manifest["context_profile_label"],
                "occurrence_index": occurrence["occurrence_index"],
                "operation": sass["operation"],
                "encoding": tuple(int(word, 16) for word in sass["encoding_words"]),
            }
            all_occurrences.append(record)
            if attribution["optimization"] == "O3" and manifest["context_profile_label"] == "runtime_zero":
                runtime_records.append(record)

    guard_index_values = defaultdict(Counter)
    guard_probe_occurrence_count = 0
    enable_index_values = defaultdict(Counter)
    enable_negate_values = defaultdict(Counter)
    for record in all_occurrences:
        if record["optimization"] != "O3":
            continue
        predicate, _, operands = operation_parts(record["operation"])
        if record["context_profile"] in {
            "predicate_index_up0",
            *PREDICATE_PRESSURE_PROFILES,
        } and predicate and re.fullmatch(r"@UP[0-6]", predicate):
            index = int(predicate[3:])
            guard_probe_occurrence_count += 1
            guard_index_values[index][(record["encoding"][0] >> 12) & 0x7] += 1
        enable_tokens = [
            operand
            for operand in operands
            if re.fullmatch(r"!?UP(?:[0-6]|T)", operand)
        ]
        if len(enable_tokens) != 1:
            continue
        enable = enable_tokens[0]
        expected_index = 7 if enable.lstrip("!") == "UPT" else int(enable[2:])
        enable_index_values[enable][(record["encoding"][1] >> 23) & 0x7] += 1
        enable_negate_values[enable][(record["encoding"][1] >> 26) & 0x1] += 1

    reuse_rules = []
    for collector_side, token in (("A", ".A_REUSE"), ("B", ".B_REUSE")):
        deltas = []
        witness_count = 0
        for manifest in manifest_by_implementation.values():
            if manifest["context_profile_label"] != "runtime_zero":
                continue
            steps = manifest["semantic_form"]["collector_steps"]
            if [step["collector_op"] for step in steps] != ["fill", "use"]:
                continue
            is_b_collector = manifest["semantic_form"]["variant"].startswith("mma.ws")
            if (collector_side == "B") != is_b_collector:
                continue
            attribution = attribution_by_key[(manifest["source_implementation_id"], "O3")]
            left = attribution["occurrences"][0]["sass_target"]
            right = attribution["occurrences"][1]["sass_target"]
            if left["operation"] != right["operation"].replace(token, ""):
                raise ValueError(f"cannot isolate {token} in {attribution['case_label']}")
            deltas.append(
                encoding_delta(
                    tuple(int(word, 16) for word in left["encoding_words"]),
                    tuple(int(word, 16) for word in right["encoding_words"]),
                )
            )
            witness_count += 1
        summary = summarize_encoding_deltas(deltas)
        summary.update(
            {
                "collector_side": collector_side,
                "sass_token": token,
                "witness_count": witness_count,
                "interpretation": "stable modifier payload plus variable scheduling/control bits",
            }
        )
        reuse_rules.append(summary)

    manifest_by_design_profile = defaultdict(dict)
    for manifest in manifest_by_implementation.values():
        manifest_by_design_profile[
            (manifest["semantic_form_id"], manifest["source_variant_id"])
        ][manifest["context_profile_label"]] = manifest
    polarity_deltas = []
    presence_deltas = []
    for profiles in manifest_by_design_profile.values():
        if not {"runtime_zero", "guard_positive", "guard_negative"}.issubset(profiles):
            continue
        baseline = attribution_by_key[(profiles["runtime_zero"]["source_implementation_id"], "O3")]
        positive = attribution_by_key[(profiles["guard_positive"]["source_implementation_id"], "O3")]
        negative = attribution_by_key[(profiles["guard_negative"]["source_implementation_id"], "O3")]
        for base_occurrence, positive_occurrence, negative_occurrence in zip(
            baseline["occurrences"], positive["occurrences"], negative["occurrences"], strict=True
        ):
            base_sass = base_occurrence["sass_target"]
            positive_sass = positive_occurrence["sass_target"]
            negative_sass = negative_occurrence["sass_target"]
            positive_body = DIRECT_GUARD_RE.sub("", positive_sass["operation"])
            negative_body = DIRECT_GUARD_RE.sub("", negative_sass["operation"])
            if positive_body == negative_body and positive_sass["operation"].startswith("@UP") and negative_sass["operation"].startswith("@!UP"):
                polarity_deltas.append(
                    encoding_delta(
                        tuple(int(word, 16) for word in positive_sass["encoding_words"]),
                        tuple(int(word, 16) for word in negative_sass["encoding_words"]),
                    )
                )
            if base_sass["operation"] == positive_body and not DIRECT_GUARD_RE.match(base_sass["operation"]) and positive_sass["operation"].startswith("@UP"):
                presence_deltas.append(
                    encoding_delta(
                        tuple(int(word, 16) for word in base_sass["encoding_words"]),
                        tuple(int(word, 16) for word in positive_sass["encoding_words"]),
                    )
                )

    standard_records = defaultdict(lambda: defaultdict(list))
    block_records = defaultdict(lambda: defaultdict(list))
    for record in runtime_records:
        manifest = record["manifest"]
        semantic = manifest["semantic_form"]
        _, _, operands = operation_parts(record["operation"])
        operand_text = ", ".join(operands)
        steps = tuple(
            (step["collector_op"], step["collector_buffer"], step["ashift"])
            for step in semantic["collector_steps"]
        )
        common_key = (
            semantic["variant"],
            semantic["cta_group"],
            semantic["a_form"],
            semantic["zero_column_mask"],
            record["occurrence_index"],
            steps,
            manifest["source_variant"]["collector_spelling"],
            operand_text,
        )
        if semantic["kind"] in {"f16", "tf32", "f8f6f4", "i8"}:
            standard_records[common_key][semantic["kind"]].append(record)
        if semantic["kind"] in BLOCK_SCALE_KINDS:
            block_records[common_key][
                (semantic["kind"], semantic["scale_vector_semantics"])
            ].append(record)

    standard_kind_pairs = []
    for left_kind, right_kind in (
        ("f16", "tf32"),
        ("f16", "f8f6f4"),
        ("f16", "i8"),
        ("f8f6f4", "i8"),
    ):
        deltas = []
        witness_groups = 0
        for variants in standard_records.values():
            group_deltas = []
            for left in variants.get(left_kind, ()):
                for right in variants.get(right_kind, ()):
                    group_deltas.append(encoding_delta(left["encoding"], right["encoding"]))
            if group_deltas:
                witness_groups += 1
                deltas.extend(group_deltas)
        summary = summarize_encoding_deltas(deltas)
        summary.update(
            {
                "left_kind": left_kind,
                "right_kind": right_kind,
                "witness_group_count": witness_groups,
            }
        )
        standard_kind_pairs.append(summary)

    block_family_transitions = []
    for a_form in ("smem_descriptor", "tmem_address"):
        deltas = []
        witness_groups = 0
        for key, variants in block_records.items():
            if key[2] != a_form:
                continue
            group_deltas = []
            for left in variants.get(("mxf4", "block32"), ()):
                for right in variants.get(("mxf8f6f4", "scale_vec::1X"), ()):
                    group_deltas.append(encoding_delta(left["encoding"], right["encoding"]))
            if group_deltas:
                witness_groups += 1
                deltas.extend(group_deltas)
        summary = summarize_encoding_deltas(deltas)
        summary.update(
            {
                "left_family": "UTCOMMA",
                "right_family": "UTCQMMA",
                "a_form": a_form,
                "witness_group_count": witness_groups,
            }
        )
        block_family_transitions.append(summary)

    implicit_aliases = []
    for left_value, right_value, label in (
        (("mxf4", "block32"), ("mxf4", "scale_vec::2X"), "mxf4 block32 ↔ 2X"),
        (("mxf4", "block32"), ("mxf4nvf4", "block32"), "mxf4 ↔ mxf4nvf4 at block32"),
        (("mxf4", "block32"), ("mxf4nvf4", "scale_vec::2X"), "mxf4 block32 ↔ mxf4nvf4 2X"),
        (("mxf4nvf4", "block16"), ("mxf4nvf4", "scale_vec::4X"), "mxf4nvf4 block16 ↔ 4X"),
    ):
        pair_count = 0
        witness_group_count = 0
        same_operation_count = 0
        same_encoding_count = 0
        for variants in block_records.values():
            group_pairs = 0
            for left in variants.get(left_value, ()):
                for right in variants.get(right_value, ()):
                    group_pairs += 1
                    pair_count += 1
                    same_operation_count += left["operation"] == right["operation"]
                    same_encoding_count += left["encoding"] == right["encoding"]
            witness_group_count += bool(group_pairs)
        implicit_aliases.append(
            {
                "label": label,
                "left": list(left_value),
                "right": list(right_value),
                "witness_group_count": witness_group_count,
                "pair_count": pair_count,
                "same_operation_count": same_operation_count,
                "same_encoding_count": same_encoding_count,
            }
        )

    slot_specs = (
        ("source_a", 0, 0, 24),
        ("source_b", 1, 0, 32),
        ("destination", 2, 1, 0),
        ("auxiliary_mask_or_metadata", 3, 0, 40),
    )
    slot_results = []
    idesc_pair_count = 0
    idesc_pair_mismatch_count = 0
    idesc_pressure_count = 0
    idesc_pressure_mismatch_count = 0
    enable_values = Counter()
    extra_values = Counter()
    extra_mismatch_count = 0
    for name, operand_index, word_index, lsb in slot_specs:
        checked = 0
        mismatches = 0
        values = Counter()
        for record in all_occurrences:
            _, _, operands = operation_parts(record["operation"])
            match = REGISTER_RE.search(operands[operand_index])
            if not match or match.group(1) != "UR":
                continue
            value = int(match.group(2))
            checked += 1
            values[value] += 1
            if ((record["encoding"][word_index] >> lsb) & 0xFF) != value:
                mismatches += 1
        slot_results.append(
            {
                "slot": name,
                "word": word_index,
                "lsb": lsb,
                "width": 8,
                "checked_occurrence_count": checked,
                "mismatch_count": mismatches,
                "observed_register_values": sorted(values),
            }
        )
    for record in all_occurrences:
        _, _, operands = operation_parts(record["operation"])
        auxiliary = REGISTER_RE.search(operands[3])
        idesc = REGISTER_RE.search(operands[4])
        if auxiliary and idesc and auxiliary.group(1) == idesc.group(1) == "UR":
            idesc_pair_count += 1
            mismatch = int(int(idesc.group(2)) != (int(auxiliary.group(2)) ^ 1))
            idesc_pair_mismatch_count += mismatch
            if record["context_profile"] == "idesc_pair_pressure":
                idesc_pressure_count += 1
                idesc_pressure_mismatch_count += mismatch
        enable = REGISTER_RE.search(operands[-1])
        if enable and enable.group(1) == "UP":
            enable_values[int(enable.group(2))] += 1
        if len(operands) >= 7:
            extra = REGISTER_RE.search(operands[5])
            if extra and extra.group(1) == "UR":
                value = int(extra.group(2))
                extra_values[value] += 1
                extra_mismatch_count += int(((record["encoding"][0] >> 48) & 0xFF) != value)
    slot_results.append(
        {
            "slot": "extra_scale_or_zero_mask",
            "word": 0,
            "lsb": 48,
            "width": 8,
            "checked_occurrence_count": sum(extra_values.values()),
            "mismatch_count": extra_mismatch_count,
            "observed_register_values": sorted(extra_values),
        }
    )

    single_slot_pair_count = 0
    single_slot_pair_mismatch_count = 0
    for difference in read_jsonl(differences_path):
        if difference["optimization"] != "O3" or difference["treatment_profile"] != "lane0_issuer":
            continue
        for occurrence in difference["core"]["occurrences"]:
            if not occurrence["allocation"]["renumber_only"]:
                continue
            baseline_operation = occurrence["baseline"]["sass"]["operation"]
            treatment_operation = occurrence["treatment"]["sass"]["operation"]
            baseline_registers = REGISTER_RE.findall(baseline_operation)
            treatment_registers = REGISTER_RE.findall(treatment_operation)
            changed = [
                index
                for index, pair in enumerate(zip(baseline_registers, treatment_registers, strict=True))
                if pair[0] != pair[1]
            ]
            if len(changed) != 1:
                continue
            index = changed[0]
            if index != 5 or baseline_registers[index][0] != "UR" or treatment_registers[index][0] != "UR":
                continue
            baseline_value = int(baseline_registers[index][1])
            treatment_value = int(treatment_registers[index][1])
            baseline_word = int(occurrence["baseline"]["sass"]["encoding_words"][0], 16)
            treatment_word = int(occurrence["treatment"]["sass"]["encoding_words"][0], 16)
            single_slot_pair_count += 1
            single_slot_pair_mismatch_count += int(
                ((baseline_word >> 48) & 0xFF) != baseline_value
                or ((treatment_word >> 48) & 0xFF) != treatment_value
            )

    return {
        "method": "paired O3 evidence for semantic fields plus all-optimization direct register-field correlation",
        "reuse": reuse_rules,
        "predicate": {
            "presence": summarize_encoding_deltas(presence_deltas),
            "polarity": summarize_encoding_deltas(polarity_deltas),
            "guard_index": {
                "field": "word 0 [14:12]",
                "unpredicated_sentinel": 7,
                "probe_occurrence_count": guard_probe_occurrence_count,
                "observed": [
                    {
                        "sass_predicate": f"UP{index}",
                        "expected_field_value": index,
                        "field_value_counts": {
                            str(value): count
                            for value, count in sorted(values.items())
                        },
                    }
                    for index, values in sorted(guard_index_values.items())
                ],
            },
            "enable_index": {
                "field": "word 1 [25:23]",
                "negate_bit": "word 1 [26]",
                "true_sentinel": 7,
                "observed": [
                    {
                        "sass_predicate": token,
                        "expected_index": (
                            7 if token.lstrip("!") == "UPT" else int(token[2:])
                        ),
                        "field_value_counts": {
                            str(value): count
                            for value, count in sorted(enable_index_values[token].items())
                        },
                        "negate_value_counts": {
                            str(value): count
                            for value, count in sorted(enable_negate_values[token].items())
                        },
                    }
                    for token in sorted(enable_index_values)
                ],
            },
        },
        "opcode_layout": analyze_opcode_layout(runtime_records),
        "scheduling_control": analyze_scheduling_control(all_occurrences),
        "sparse_encoding_aliases": analyze_sparse_encoding_aliases(runtime_records),
        "standard_kind_pairs": standard_kind_pairs,
        "block_family_transitions": block_family_transitions,
        "implicit_kind_scale_aliases": implicit_aliases,
        "register_slots": {
            "fields": slot_results,
            "idesc_adjacent_pair": {
                "relation": "idesc_ur = auxiliary_ur XOR 1",
                "checked_occurrence_count": idesc_pair_count,
                "mismatch_count": idesc_pair_mismatch_count,
                "independent_field_status": "not observed; current allocation encodes the even/odd pair through the auxiliary slot",
                "pressure_probe": {
                    "checked_occurrence_count": idesc_pressure_count,
                    "mismatch_count": idesc_pressure_mismatch_count,
                    "live_uniform_64bit_values": 8,
                },
            },
            "enable_predicate": {
                "observed_values": sorted(enable_values),
                "occurrence_count": sum(enable_values.values()),
                "field_status": "constant UP0 in current matrix; independent slot location not isolated",
            },
            "extra_slot_single_change_pairs": {
                "pair_count": single_slot_pair_count,
                "mismatch_count": single_slot_pair_mismatch_count,
            },
        },
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
    extended_encoding = report["extended_encoding"]
    extended_contexts = report["extended_contexts"]
    canonical = report["canonical_mapping"]
    inverse = report["inverse"]
    lines = [
        "# `tcgen05.mma` 可预测映射与逆向可恢复性规则",
        "",
        "> 本页由 `analyze_mapping_rules.py` 从 expanded manifest、O3 核心 SASS attribution 和逐配对 context differences 自动生成。结论只适用于当前 PTX 9.0、`sm_110a`、生成矩阵和工具链。",
        "",
        f"> 当前输入与工具链已写入生成 JSON：ptxas SHA-256 `{report['toolchain']['ptxas_sha256']}`，nvdisasm SHA-256 `{report['toolchain']['nvdisasm_sha256']}`。",
        "",
        "## guard 编译降级的精确分类",
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
            "## lane-0 issuer（发射线程）的核心重编号条件",
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
            "## 扩展 issuer 与 producer 编译降级",
            "",
        ]
    )
    if extended_contexts["status"] == "COMPLETE":
        lines.extend(
            [
                f"新增 issuer/producer profile 已完成 O3 单因素配对，跨四种 branch issuer 的分类不一致数为 {extended_contexts['branch_issuer_cross_profile_mismatch_count']}，全部手写公式 mismatch={extended_contexts['formula_mismatch_count']}。",
                "",
                "| profile | design | 核心结果与数量 | 核心 mnemonic 变化 | 完整 kernel 序列变化 | 指令数变化 | 公式 |",
                "|---|---:|---|---:|---:|---:|---|",
            ]
        )
        for profile, result in extended_contexts["profiles"].items():
            outcomes = "；".join(f"`{name}` {count}" for name, count in result["outcome_counts"].items())
            lines.append(f"| `{profile}` | {result['design_count']} | {outcomes} | {result['core_mnemonic_changed_count']} | {result['kernel_normalized_sequence_changed_count']} | {result['kernel_instruction_count_changed_count']} | {result['formula']} |")
        lines.extend(
            [
                "",
                "四种 branch issuer（lane 0、lane 31、动态 lane、CTA thread 0）对核心映射使用同一条 168/984 重编号分类；差异只落在外围线程标识读取、比较、分支和寄存器布局。compound predicated issuer 的规则更简单：双 occurrence collector 序列只谓词化第一条，单 occurrence 形态使用外围控制流。",
                "",
                "identity producer 在 O3 完全消除；非恒等算术和分支选择 producer 保留外围计算并使全部核心发生纯重编号；global-load producer 保持核心助记符和规范操作不变，其中 468 个设计纯重编号、684 个布局稳定。",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"生成器已经加入扩展 issuer/producer profile，但当前 attribution 尚未包含：`{', '.join(extended_contexts['missing_profiles'])}`。运行完整 `check_all.sh` 后本节会自动生成分类、公式和反例计数。",
                "",
            ]
        )
    lines.extend(
        [
            "## PTX 源码别名（source alias）的编码等价性",
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
            "候选配对会因等价 source spelling 和同组重复实例形成笛卡尔积，因此表中把独立 witness 组作为证据规模，把候选配对仅作为一致性重复数；每组的 witness ID、左右 PTX、SASS、encoding、置位 mask 和清位 mask 均保存在生成 JSON。所有行都只有一个稳定 XOR mask，其中 `.4X` 是清位，其余当前字段是置位或表中注明的方向；B buffer 的 `B0/B1/B2/B3` 对应 word 1 的两位字段 `0x0000/0x8000/0x10000/0x18000`。这里描述的是当前 Thor 工具链输出，不把 bit 编号外推到其他架构。`A/B_REUSE` 和 predicate 因伴随调度控制变化而在下一节单独分解。",
            "",
            "## opcode、kind 与隐式 scale 的编码",
            "",
            "标准非 block-scale kind 在具体操作数完全相同的 O3 pair 上形成 word 1 的两位字段；每一行均只有一个 XOR mask：",
            "",
            "| kind 变化 | witness 组 | pair | word 0 XOR | word 1 XOR | 方向 |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for rule in extended_encoding["standard_kind_pairs"]:
        mask = rule["xor_masks"][0]["encoding_words"]
        set_nonzero = any(int(word, 16) for word in rule["stable_set_words"])
        clear_nonzero = any(int(word, 16) for word in rule["stable_clear_words"])
        direction = "编码相同" if not set_nonzero and not clear_nonzero else "置位" if set_nonzero and not clear_nonzero else "清位" if clear_nonzero and not set_nonzero else "混合"
        lines.append(f"| `{rule['left_kind']} → {rule['right_kind']}` | {rule['witness_group_count']} | {rule['pair_count']} | `{mask[0]}` | `{mask[1]}` | {direction} |")
    lines.extend(
        [
            "",
            "因此 `f16` 与 `tf32` 在当前动态 `idesc` 契约下是核心机器编码别名（alias）；`f16/tf32 = 0b00`、`i8 = 0b01`、`f8f6f4 = 0b11` 对应 word 1 的 `0x300` 两位字段。`UTCOMMA` 相对 `UTCQMMA` 还组合使用 word 0 的 opcode 位，不能只看这两位判断全部 block-scale 家族。",
            "",
            "在 block-scale 且具体寄存器完全相同的 pair 中，`UTCOMMA → UTCQMMA` 的 composite opcode 变化还取决于 A 来源：",
            "",
            "| 家族变化 | A 来源 | witness 组 | pair | word 0 XOR | word 1 XOR |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for rule in extended_encoding["block_family_transitions"]:
        mask = rule["xor_masks"][0]["encoding_words"]
        lines.append(f"| `{rule['left_family']} → {rule['right_family']}` | `{rule['a_form']}` | {rule['witness_group_count']} | {rule['pair_count']} | `{mask[0]}` | `{mask[1]}` |")
    opcode_layout = extended_encoding["opcode_layout"]
    lines.extend(
        [
            "",
            "word 0 的高两位、低 opcode 子字段和 word 1 的 kind 两位共同决定这一家族转换；SS 与 TS 的低 opcode mask 不同，所以不能把 `UTCOMMA/UTCQMMA` 简化成单一 bit。",
            "",
            "全矩阵按 SASS family、A 来源、kind 和 PTX variant 分组后的 opcode composite 值保存在生成 JSON 的 `extended_encoding.opcode_layout.observed_rows`；字段模型固定为 word 0 `[63:56] + [11:0]`、word 1 `[9:8]`，guard 使用 word 0 `[15:12]` 的独立区域。",
            "",
            "以下 block-scale 形态在所有严格配对中连具体 SASS 操作和两个 encoding word 都相同，说明 kind/scale 的部分区别没有独立进入核心机器码：",
            "",
            "| 隐式 kind/scale alias | 独立 witness 组 | pair | 操作相同 | 编码相同 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for alias in extended_encoding["implicit_kind_scale_aliases"]:
        lines.append(f"| `{alias['label']}` | {alias['witness_group_count']} | {alias['pair_count']} | {alias['same_operation_count']} | {alias['same_encoding_count']} |")
    lines.extend(
        [
            "",
            "## `A/B_REUSE` 与 predicate（谓词）编码",
            "",
            "`fill → use` 的第二条核心指令同时改变 REUSE payload 和高位调度/控制字段。对全部 pair 求方向交集后，可以把稳定 modifier 位与可变控制位分开：",
            "",
            "| 变化 | pair | 稳定置位 word 0 | 稳定置位 word 1 | 稳定清位 word 0 | 可变 word 1 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for rule in extended_encoding["reuse"]:
        lines.append(f"| `.{rule['collector_side']}_REUSE` | {rule['pair_count']} | `{rule['stable_set_words'][0]}` | `{rule['stable_set_words'][1]}` | `{rule['stable_clear_words'][0]}` | `{rule['variable_words'][1]}` |")
    predicate_presence = extended_encoding["predicate"]["presence"]
    predicate_polarity = extended_encoding["predicate"]["polarity"]
    guard_index = extended_encoding["predicate"]["guard_index"]
    enable_index = extended_encoding["predicate"]["enable_index"]
    lines.extend(
        [
            "",
            "`A_REUSE` 的稳定 payload 是 word 1 置位 `0x0000000000400000`，`B_REUSE` 是 word 1 置位 `0x0000000000040000`；两者共同出现的 word 1 高位变化属于调度/控制字段，不能并入 REUSE modifier mask。",
            "",
            "| predicate 配对 | pair | 稳定变化 | 其他变化 |",
            "|---|---:|---|---|",
            f"| 无核心 predicate → `@UP1` | {predicate_presence['pair_count']} | word 0 清除 `{predicate_presence['stable_clear_words'][0]}` | word 1 高位随调度布局变化 `{predicate_presence['variable_words'][1]}` |",
            f"| `@UP1 → @!UP1` | {predicate_polarity['pair_count']} | word 0 置位 `{predicate_polarity['stable_set_words'][0]}` | 无 |",
            "",
        ]
    )
    if guard_index["observed"]:
        guard_probe_counts = "、".join(
            f"`{item['sass_predicate']}` {sum(item['field_value_counts'].values())} 条"
            for item in guard_index["observed"]
        )
        enable_probe_counts = "、".join(
            f"`{item['sass_predicate']}` {sum(item['field_value_counts'].values())} 条"
            for item in enable_index["observed"]
            if item["sass_predicate"] in {f"UP{index}" for index in range(1, 7)}
        )
        lines.extend(
            [
                "定向谓词活跃压力探针进一步冻结完整 selector：核心 guard 的 UP 编号直接写入 word 0 `[14:12]`，`UP0..UP6 → 0..6`，值 7 表示无 guard；word 0 bit 15 是 negate。",
                "",
                f"guard selector 的定向证据共 {guard_index['probe_occurrence_count']} 个 occurrence（{guard_probe_counts}）。enable 谓词使用独立字段：word 1 `[25:23]` 直接编码 `UP0..UP6`，值 7 表示 `UPT`，word 1 bit 26 是 enable negate；稀有编号定向证据为 {enable_probe_counts}，`UP0` 与哨兵值另由常规矩阵提供大量重复。完整逐值计数见生成 JSON。",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "当前 attribution 尚未包含 v4 定向谓词探针；完成 Thor 重跑后，本节会自动生成 `UP0..UP6` guard/enable selector 与哨兵值的逐值断言。",
                "",
            ]
        )
    lines.extend(
        [
            "## 核心寄存器槽位 bitfield（位字段）",
            "",
            "把全部 O0/O1/O2/O3 attribution 中反汇编显示的 UR 编号直接回放到 encoding word，得到以下五个 8-bit 槽位，所有检查均为零 mismatch：",
            "",
            "| SASS 操作数角色 | encoding 字段 | occurrence | 观测 UR 值 | mismatch |",
            "|---|---|---:|---|---:|",
        ]
    )
    for field in extended_encoding["register_slots"]["fields"]:
        msb = field["lsb"] + field["width"] - 1
        values = ",".join(str(value) for value in field["observed_register_values"])
        lines.append(f"| `{field['slot']}` | word {field['word']} `[{msb}:{field['lsb']}]` | {field['checked_occurrence_count']} | `{values}` | {field['mismatch_count']} |")
    idesc_pair = extended_encoding["register_slots"]["idesc_adjacent_pair"]
    extra_pairs = extended_encoding["register_slots"]["extra_slot_single_change_pairs"]
    enable_predicate = extended_encoding["register_slots"]["enable_predicate"]
    lines.extend(
        [
            "",
            f"`idesc[URn]` 在 {idesc_pair['checked_occurrence_count']} 条 occurrence 中始终满足 `{idesc_pair['relation']}`，mismatch={idesc_pair['mismatch_count']}；当前分配把 auxiliary/idesc 作为偶/奇相邻对，尚未观察到独立 idesc 槽位。extra 槽位另有 {extra_pairs['pair_count']} 个只改变该 UR 的上下文 pair 验证，mismatch={extra_pairs['mismatch_count']}。",
            "",
            (
                f"常规矩阵中的 enable predicate 主要为 `{','.join('UP' + str(value) for value in enable_predicate['observed_values'])}`，共 {enable_predicate['occurrence_count']} 条动态谓词 occurrence；v4 定向 sweep 通过同时保持七个统一谓词活跃，独立恢复 word 1 `[25:23]` 字段。"
                if guard_index["observed"]
                else f"当前已发布 attribution 中的 enable predicate 主要为 `{','.join('UP' + str(value) for value in enable_predicate['observed_values'])}`，共 {enable_predicate['occurrence_count']} 条动态谓词 occurrence；v4 定向 sweep 将在 Thor 重跑后把 word 1 `[25:23]` 的逐编号证据写入本报告。"
            ),
            "",
            "## 可回放的正向与逆向规则",
            "",
            f"分析器已经生成 [`canonical_mapping_rules.json`](../../results/rule-mining/canonical_mapping_rules.json)：包含 {canonical['forward_rule_count']} 条 semantic-form→核心 SASS/semantic-payload 正向规则和 {canonical['inverse_rule_count']} 条 SASS/semantic-payload→候选 semantic-form 逆向规则；其中 {canonical['ambiguous_inverse_rule_count']} 条逆向规则必须返回候选集合。正向→逆向逐条回放 mismatch={canonical['roundtrip_mismatch_count']}。",
            "",
            "逆向候选规模分布为 " + "、".join(
                f"{candidate_count} 个候选的规则 {rule_count} 条"
                for candidate_count, rule_count in canonical["candidate_count_distribution"].items()
            ) + f"；最大候选集合为 {canonical['max_candidate_count']}。因此这里的“逆向规则”是可枚举候选关系，不是单值反编译器。",
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
            "| 核心 SASS signature | PTX 目标拼写 | occurrence | 实际歧义字段 |",
            "|---|---:|---:|---|",
        ]
    )
    for collision in inverse["top_collision_groups"][:6]:
        fields = "；".join(
            f"`{field}`=" + ",".join(f"`{value}`" for value in values)
            for field, values in collision["ambiguous_fields"].items()
        ) or "仅 PTX 拼写不同"
        lines.append(f"| `{collision['sass_signature']}` | {collision['ptx_spelling_count']} | {collision['occurrence_count']} | {fields} |")
    lines.extend(["", "表中只列出现次数最高的六组；全部 collision、每组候选 PTX 拼写与字段取值见[生成 JSON](../../results/rule-mining/mapping_rule_analysis.json)。", ""])
    lines.extend(
        [
            "## 规则使用边界",
            "",
            "- guard 与 issuer 的分类规则来自当前有限字段集合；加入 descriptor 常量、真实非恒等 producer 或其他工具链版本后必须重新运行分析器。",
            "- 核心 SASS 的可恢复性不包含外围指令。某些 source/context 信息虽然不在核心中，仍可能从完整 kernel 恢复。",
            "- 逆向 signature 分析会规范化具体寄存器编号，因此不能用该小节预测物理寄存器分配；上一节的机器编码位结论使用的是未规范化且寄存器文本完全相同的严格 witness，不受此限制。",
            "- descriptor 的动态内容尚未枚举，因此 `idesc`、SMEM descriptor 的形状、类型、布局、stride 和 swizzle 位型仍属于未解决层。",
            "- v4 新增的 opcode composite、`A/B_REUSE`、完整 predicate selector、隐式 kind/scale 别名、寄存器槽位和扩展 issuer/producer 机制目前只在一组 Thor 工具链二进制上完成 O0–O3 验证；独立双二进制复现只覆盖 v3 范围，不能把 v3 的复现强度自动外推到 v4 新增结论。",
            "",
            "## 证据入口",
            "",
            "- 规则挖掘器：[`../../analyze_mapping_rules.py`](../../analyze_mapping_rules.py)",
            "- 完整机器可读结果：[`../../results/rule-mining/mapping_rule_analysis.json`](../../results/rule-mining/mapping_rule_analysis.json)",
            "- 生成 manifest：[`../../results/expanded/sources/manifest.jsonl`](../../results/expanded/sources/manifest.jsonl)",
            "- 核心 SASS attribution 汇总：[`../../results/expanded/sass/sass_report.json`](../../results/expanded/sass/sass_report.json)；逐记录 `sass_attribution.jsonl` 不随 Git 发布，使用前须核对本页生成 JSON 中记录的输入 SHA-256",
            "- 上下文统计：[`../../Docs/tcgen05_mma_上下文差分报告.md`](../../Docs/tcgen05_mma_上下文差分报告.md)",
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
    comparison_report_path = args.differences.parent / "comparison_report.json"
    if comparison_report_path.is_file():
        comparison_report = json.loads(comparison_report_path.read_text(encoding="utf-8"))
        expected_hashes = {
            args.manifest: comparison_report.get("input_manifest_sha256"),
            args.attribution: comparison_report.get("input_sass_attribution_sha256"),
            args.differences: comparison_report.get("differences_sha256"),
        }
        mismatched_inputs = []
        for path, expected in expected_hashes.items():
            if not expected:
                continue
            observed = sha256_file(path)
            if observed != expected:
                mismatched_inputs.append(f"{path}: expected {expected}, observed {observed}")
        if mismatched_inputs:
            raise ValueError(
                "rule-mining inputs do not match context comparison provenance; "
                "refusing to replace published output:\n" + "\n".join(mismatched_inputs)
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
    extended_encoding = analyze_extended_encoding(
        args.attribution, args.differences, manifest_by_implementation
    )
    expected_reuse_masks = {
        "A": ["0x0000000000000000", "0x0000000000400000"],
        "B": ["0x0000000000000000", "0x0000000000040000"],
    }
    for rule in extended_encoding["reuse"]:
        if rule["pair_count"] == 0 or rule["stable_set_words"] != expected_reuse_masks[rule["collector_side"]]:
            raise ValueError(f"reuse payload field changed: {rule['collector_side']}")
    predicate_polarity = extended_encoding["predicate"]["polarity"]
    if predicate_polarity["pair_count"] == 0 or predicate_polarity["xor_masks"] != [
        {"encoding_words": ["0x0000000000008000", "0x0000000000000000"], "pair_count": predicate_polarity["pair_count"]}
    ]:
        raise ValueError("predicate polarity field changed")
    predicate_presence = extended_encoding["predicate"]["presence"]
    if predicate_presence["pair_count"] == 0 or predicate_presence["stable_clear_words"][0] != "0x0000000000006000":
        raise ValueError("predicate selector field changed")
    expected_kind_masks = {
        ("f16", "tf32"): ["0x0000000000000000", "0x0000000000000000"],
        ("f16", "f8f6f4"): ["0x0000000000000000", "0x0000000000000300"],
        ("f16", "i8"): ["0x0000000000000000", "0x0000000000000100"],
        ("f8f6f4", "i8"): ["0x0000000000000000", "0x0000000000000200"],
    }
    for rule in extended_encoding["standard_kind_pairs"]:
        expected = expected_kind_masks[(rule["left_kind"], rule["right_kind"])]
        if rule["pair_count"] == 0 or len(rule["xor_masks"]) != 1 or rule["xor_masks"][0]["encoding_words"] != expected:
            raise ValueError(f"standard kind field changed: {rule['left_kind']}->{rule['right_kind']}")
    expected_block_family_masks = {
        "smem_descriptor": ["0xc000000000000800", "0x0000000000000300"],
        "tmem_address": ["0xc000000000000600", "0x0000000000000300"],
    }
    for rule in extended_encoding["block_family_transitions"]:
        expected = expected_block_family_masks[rule["a_form"]]
        if rule["pair_count"] == 0 or len(rule["xor_masks"]) != 1 or rule["xor_masks"][0]["encoding_words"] != expected:
            raise ValueError(f"block opcode family transition changed: {rule['a_form']}")
    for alias in extended_encoding["implicit_kind_scale_aliases"]:
        if alias["pair_count"] == 0 or alias["same_operation_count"] != alias["pair_count"] or alias["same_encoding_count"] != alias["pair_count"]:
            raise ValueError(f"implicit kind/scale alias changed: {alias['label']}")
    sparse_aliases = extended_encoding["sparse_encoding_aliases"]
    if not sparse_aliases["pair_count"] or sparse_aliases["different_semantic_payload_count"]:
        raise ValueError("dense/sparse semantic-payload alias rule changed")
    scheduling_control = extended_encoding["scheduling_control"]
    if int(scheduling_control["observed_variable_mask"], 16) & 0x01F2000000000000 != 0x01F2000000000000:
        raise ValueError("scheduling/control codebook no longer covers the REUSE-associated variable mask")
    register_slots = extended_encoding["register_slots"]
    if any(field["checked_occurrence_count"] == 0 or field["mismatch_count"] for field in register_slots["fields"]):
        raise ValueError("register slot field correlation failed")
    if register_slots["idesc_adjacent_pair"]["mismatch_count"]:
        raise ValueError("idesc adjacent-pair relation changed")
    if register_slots["extra_slot_single_change_pairs"]["pair_count"] == 0 or register_slots["extra_slot_single_change_pairs"]["mismatch_count"]:
        raise ValueError("extra register slot paired verification failed")
    requires_predicate_probes = any(
        manifest["source_variant"].get("kernel_template") == "thor_tcgen05_mma_v4"
        for manifest in manifests
    )
    if requires_predicate_probes:
        guard_index = extended_encoding["predicate"]["guard_index"]
        guard_observed = {
            int(row["sass_predicate"][2:]): row["field_value_counts"]
            for row in guard_index["observed"]
        }
        if guard_observed != {
            index: {str(index): guard_observed.get(index, {}).get(str(index), 0)}
            for index in range(7)
        } or any(not next(iter(values.values()), 0) for values in guard_observed.values()):
            raise ValueError(f"guard predicate-index field changed: {guard_observed}")
        enable_observed = {
            row["sass_predicate"]: row
            for row in extended_encoding["predicate"]["enable_index"]["observed"]
        }
        for index in range(7):
            row = enable_observed.get(f"UP{index}")
            if row is None or row["field_value_counts"] != {str(index): row["field_value_counts"].get(str(index), 0)}:
                raise ValueError(f"enable predicate-index field changed at UP{index}")
        if enable_observed.get("UPT", {}).get("field_value_counts") != {"7": enable_observed.get("UPT", {}).get("field_value_counts", {}).get("7", 0)}:
            raise ValueError("enable UPT selector sentinel changed")
        if enable_observed.get("!UPT", {}).get("negate_value_counts") != {"1": enable_observed.get("!UPT", {}).get("negate_value_counts", {}).get("1", 0)}:
            raise ValueError("enable predicate negate bit changed")
        idesc_pressure = register_slots["idesc_adjacent_pair"]["pressure_probe"]
        if not idesc_pressure["checked_occurrence_count"] or idesc_pressure["mismatch_count"]:
            raise ValueError("idesc adjacent-pair pressure probe failed")
    extended_contexts = analyze_extended_context_rules(
        args.differences, manifest_by_implementation
    )
    requires_extended_contexts = any(
        manifest["source_variant"].get("kernel_template") in {"thor_tcgen05_mma_v3", "thor_tcgen05_mma_v4"}
        for manifest in manifests
    )
    if extended_contexts["status"] == "FAIL" or (
        requires_extended_contexts and extended_contexts["status"] != "COMPLETE"
    ):
        raise ValueError(
            "extended producer/issuer rule verification failed: "
            f"status={extended_contexts['status']}, "
            f"formula={extended_contexts['formula_mismatch_count']}, "
            f"cross_profile={extended_contexts['branch_issuer_cross_profile_mismatch_count']}"
        )
    sass_report_path = args.attribution.parent / "sass_report.json"
    compile_report_path = args.attribution.parent.parent / "compile_report.json"
    sass_report = json.loads(sass_report_path.read_text(encoding="utf-8")) if sass_report_path.is_file() else {}
    compile_report = json.loads(compile_report_path.read_text(encoding="utf-8")) if compile_report_path.is_file() else {}
    canonical_mapping = analyze_canonical_mapping(
        args.attribution, manifest_by_implementation
    )
    if canonical_mapping["roundtrip_mismatch_count"]:
        raise ValueError("canonical forward/inverse mapping roundtrip failed")
    output_dir = reset_owned_directory(
        args.output_dir,
        owner="thor_tcgen05_mapping_rule_mining",
        protected=(ROOT,),
    )
    canonical_path = output_dir / "canonical_mapping_rules.json"
    canonical_path.write_text(
        json.dumps(canonical_mapping, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = {
        "schema_version": "thor_tcgen05_mapping_rule_mining_v4",
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
        "extended_encoding": extended_encoding,
        "extended_contexts": extended_contexts,
        "canonical_mapping": {
            key: value
            for key, value in canonical_mapping.items()
            if key not in {"forward_rules", "inverse_rules"}
        } | {
            "path": canonical_path.name,
            "sha256": sha256_file(canonical_path),
        },
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

#!/usr/bin/env python3
"""Independently validate generated manifests against emitted PTX sources."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

from suite_utils import stable_hash


def read_json_lines(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from error
    return rows


def kernel_block(source: str, ordinal: int) -> str:
    begin = f"// CASE_BEGIN {ordinal:06d}"
    end = f"// CASE_END {ordinal:06d}"
    if source.count(begin) != 1 or source.count(end) != 1:
        raise ValueError(f"case {ordinal}: missing or duplicate CASE markers")
    return source.split(begin, 1)[1].split(end, 1)[0]


def validate_mma_suite(directory: Path, summary: dict, rows: list[dict]) -> dict:
    sources = sorted(directory.glob("*.ptx"))
    expected_sources = summary["source_shard_count"]
    if not sources or len(sources) != expected_sources:
        raise ValueError(
            f"source shard count mismatch: expected {expected_sources}, got {len(sources)}"
        )
    expected_rows = summary["source_implementation_count"]
    if not rows or len(rows) != expected_rows:
        raise ValueError(
            f"manifest implementation count mismatch: expected {expected_rows}, "
            f"got {len(rows)}"
        )

    source_text = {path.name: path.read_text(encoding="utf-8") for path in sources}
    if any(not text.strip() for text in source_text.values()):
        raise ValueError("generated PTX source must not be empty")

    labels = set()
    kernels = set()
    implementation_ids = set()
    semantic_ids = set()
    static_context_ids = set()
    logical_design_ids = set()
    source_variant_ids = set()
    total_occurrences = 0
    referenced_sources = Counter()

    for row in rows:
        label = row["case_label"]
        kernel = row["kernel"]
        if label in labels or kernel in kernels:
            raise ValueError(f"duplicate case label or kernel: {label} / {kernel}")
        labels.add(label)
        kernels.add(kernel)

        sf_id = stable_hash(row["semantic_form"])
        context_id = stable_hash(row["static_context_assignment"])
        variant_id = stable_hash(row["source_variant"])
        implementation_id = stable_hash(
            {
                "semantic_form_id": sf_id,
                "static_context_id": context_id,
                "source_variant_id": variant_id,
            }
        )
        expected_identity = {
            "semantic_form_id": sf_id,
            "static_context_id": context_id,
            "source_variant_id": variant_id,
            "source_implementation_id": implementation_id,
        }
        for field, expected in expected_identity.items():
            if row[field] != expected:
                raise ValueError(f"{label}: invalid {field}")
        if implementation_id in implementation_ids:
            raise ValueError(f"{label}: duplicate source implementation identity")
        implementation_ids.add(implementation_id)
        semantic_ids.add(sf_id)
        static_context_ids.add(context_id)
        source_variant_ids.add(variant_id)
        logical_design_ids.add(
            stable_hash(
                {
                    "semantic_form_id": sf_id,
                    "static_context_id": context_id,
                }
            )
        )

        source_name = row["source_shard"]
        if source_name not in source_text:
            raise ValueError(f"{label}: missing source shard {source_name}")
        referenced_sources[source_name] += 1
        ordinal_match = re.fullmatch(r"THOR_MMA_([0-9]{6})", label)
        if ordinal_match is None:
            raise ValueError(f"invalid case label: {label}")
        ordinal = int(ordinal_match.group(1))
        block = kernel_block(source_text[source_name], ordinal)
        if block.count(f".visible .entry {kernel}(") != 1:
            raise ValueError(f"{label}: kernel symbol mismatch")

        expected_comments = (
            "// semantic_form "
            + json.dumps(
                row["semantic_form"], sort_keys=True, separators=(",", ":")
            ),
            "// static_context_assignment "
            + json.dumps(
                row["static_context_assignment"],
                sort_keys=True,
                separators=(",", ":"),
            ),
            "// source_variant "
            + json.dumps(
                row["source_variant"], sort_keys=True, separators=(",", ":")
            ),
        )
        for comment in expected_comments:
            if block.count(comment) != 1:
                raise ValueError(f"{label}: manifest/source metadata mismatch")

        occurrence_matches = re.findall(
            r"// target_occurrence ([0-9]+)\n\s+([^\n]+;)", block
        )
        actual_instructions = [item[1].strip() for item in occurrence_matches]
        expected_instructions = row["target_instructions"]
        if [int(item[0]) for item in occurrence_matches] != list(
            range(len(expected_instructions))
        ):
            raise ValueError(f"{label}: occurrence indices are not contiguous")
        if actual_instructions != expected_instructions:
            raise ValueError(f"{label}: target instructions differ from manifest")
        if len(actual_instructions) != row["target_occurrence_count"]:
            raise ValueError(f"{label}: target occurrence count mismatch")
        total_occurrences += len(actual_instructions)

        context = row["static_context_assignment"]
        guard = context["target_guard"]["mode"]
        if guard == "predicate":
            polarity = context["target_guard"]["polarity"]
            prefix = "@%guard " if polarity == "positive" else "@!%guard "
            if any(not instruction.startswith(prefix) for instruction in actual_instructions):
                raise ValueError(f"{label}: target guard mismatch")
        if guard == "predicate_index_pressure":
            hold_count = context["target_guard"]["live_uniform_predicates_across_target"]
            prefix = f"@%hold{hold_count - 1} "
            if any(not instruction.startswith(prefix) for instruction in actual_instructions):
                raise ValueError(f"{label}: predicate-pressure guard mismatch")
            for index in range(hold_count):
                if f"@%hold{index} tcgen05.commit.cta_group::" not in block:
                    raise ValueError(f"{label}: predicate-pressure live use missing")
        if guard == "predicate_index_probe":
            if any(not instruction.startswith("@%guard ") for instruction in actual_instructions):
                raise ValueError(f"{label}: predicate-index guard mismatch")
        if context["enable_input_d"]["producer"] == "predicate_index_sweep":
            for index, instruction in enumerate(actual_instructions):
                if f", %hold{index};" not in instruction:
                    raise ValueError(f"{label}: enable-predicate sweep operand mismatch")
        if context["operand_producers"]["mode"] == "uniform_register_pressure_across_target":
            if block.count("tcgen05.commit.cta_group::") != 16:
                raise ValueError(f"{label}: idesc pair-pressure construction missing")
        if context["issuer"]["mode"] == "lane_zero_branch":
            if "%laneid" not in block or "@!%issuer bra" not in block:
                raise ValueError(f"{label}: lane-zero issuer construction missing")
        if context["operand_producers"]["mode"] == "identity_arithmetic_chain":
            for operation in ("add.u32", "xor.b64", "or.b64", "xor.b32"):
                if operation not in block:
                    raise ValueError(f"{label}: derived producer {operation} missing")
        if context["completion"]["mode"] == "tcgen05_commit":
            if "tcgen05.commit.cta_group::" not in block:
                raise ValueError(f"{label}: commit completion missing")

    expected_summary_counts = {
        "semantic_form_count": len(semantic_ids),
        "static_context_count": len(static_context_ids),
        "logical_design_count": len(logical_design_ids),
        "source_variant_count": len(source_variant_ids),
        "target_occurrence_count": total_occurrences,
    }
    for field, expected in expected_summary_counts.items():
        if summary[field] != expected:
            raise ValueError(
                f"summary {field} mismatch: expected {expected}, got {summary[field]}"
            )
    if set(referenced_sources) != set(source_text):
        raise ValueError("one or more source shards are not referenced by the manifest")
    emitted_kernel_count = sum(
        text.count(".visible .entry thor_tcgen05_mma_")
        for text in source_text.values()
    )
    if emitted_kernel_count != len(rows):
        raise ValueError(
            f"emitted kernel count mismatch: expected {len(rows)}, "
            f"got {emitted_kernel_count}"
        )
    return {
        "schema_version": "thor_tcgen05_source_validation_v1",
        "validation_status": "PASS",
        "source_count": len(sources),
        "source_implementation_count": len(rows),
        **expected_summary_counts,
    }


def validate_protocol_suite(directory: Path, summary: dict, rows: list[dict]) -> dict:
    sources = sorted(directory.glob("*/*.ptx"))
    expected_count = summary["case_count"]
    if not sources or len(sources) != expected_count:
        raise ValueError(
            f"protocol source count mismatch: expected {expected_count}, "
            f"got {len(sources)}"
        )
    if not rows or len(rows) != expected_count:
        raise ValueError(
            f"protocol manifest count mismatch: expected {expected_count}, got {len(rows)}"
        )
    source_paths = {str(path.relative_to(directory)): path for path in sources}
    labels = set()
    layer_counts = Counter()
    for row in rows:
        label = row["case_label"]
        if label in labels:
            raise ValueError(f"duplicate protocol case label: {label}")
        labels.add(label)
        if row["case_key_sha256"] != stable_hash(row["coordinates"]):
            raise ValueError(f"{label}: invalid case identity")
        relative_source = row["source"]
        if relative_source not in source_paths:
            raise ValueError(f"{label}: missing source {relative_source}")
        text = source_paths[relative_source].read_text(encoding="utf-8")
        if not text.strip() or text.count(f".visible .entry {label}(") != 1:
            raise ValueError(f"{label}: missing or duplicate kernel")
        if text.count("// EFFECT_SLICE_BEGIN") != 1:
            raise ValueError(f"{label}: missing effect-slice begin marker")
        if text.count("// EFFECT_SLICE_END") != 1:
            raise ValueError(f"{label}: missing effect-slice end marker")
        coordinates = "// COORDINATES " + json.dumps(
            row["coordinates"], sort_keys=True, separators=(",", ":")
        )
        if text.count(coordinates) != 1:
            raise ValueError(f"{label}: manifest/source coordinates mismatch")
        layer_counts[row["layer"]] += 1
    if dict(layer_counts) != summary["layer_case_counts"]:
        raise ValueError("protocol layer counts differ from summary")
    return {
        "schema_version": "thor_tcgen05_protocol_source_validation_v1",
        "validation_status": "PASS",
        "source_count": len(sources),
        "case_count": len(rows),
        "layer_case_counts": dict(layer_counts),
    }


def validate_directory(directory: Path) -> dict:
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    rows = read_json_lines(directory / "manifest.jsonl")
    schema = summary.get("schema_version")
    if schema in {"thor_tcgen05_mma_generator_v2", "thor_tcgen05_mma_generator_v3", "thor_tcgen05_mma_generator_v4"}:
        return validate_mma_suite(directory, summary, rows)
    if schema == "thor_tcgen05_protocol_generator_v1":
        return validate_protocol_suite(directory, summary, rows)
    raise ValueError(f"unsupported generated suite schema: {schema!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = validate_directory(args.directory)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

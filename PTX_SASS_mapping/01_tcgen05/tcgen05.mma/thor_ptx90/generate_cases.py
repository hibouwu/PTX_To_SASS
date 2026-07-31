#!/usr/bin/env python3
"""Generate a constrained tcgen05.mma matrix for NVIDIA Thor.

The default ``syntax`` mode exhaustively enumerates the legal PTX 9.0 surface
forms declared below. ``expanded`` crosses the same forms with bounded static
context profiles. Descriptor bitfields remain runtime parameters, so successful
assembly proves syntax/target support, not numerical or lifecycle correctness.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from suite_utils import reset_owned_directory, stable_hash
from validate_generated import validate_directory


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Step:
    collector_op: str | None = None
    collector_buffer: str | None = None
    ashift: bool = False


@dataclass(frozen=True)
class Case:
    variant: str
    cta_group: int
    kind: str
    a_form: str
    scale_vector: str | None
    scale_input_d: int | None
    zero_column_mask: bool
    collector_mode: str
    steps: tuple[Step, ...]
    context_profile: str


STANDARD_SCALE_INPUTS = {
    # scale-input-d is a PTX 9.0 grammar feature, but CUDA 13 ptxas rejects it
    # for sm_110a ("argument scale-inp-d-imm" is not target-supported).
    "f16": (None,),
    "tf32": (None,),
    "f8f6f4": (None,),
    "i8": (None,),
}

# PTX ISA 9.0 Table 54/55 plus the documented omitted/default spellings.
BLOCK_SCALE_VECTORS = {
    "mxf8f6f4": (None, "scale_vec::1X", "block32"),
    "mxf4": (None, "scale_vec::2X", "block32"),
    # mxf4nvf4 requires an explicit scale-vector-size qualifier.
    "mxf4nvf4": ("scale_vec::2X", "scale_vec::4X", "block16", "block32"),
}

CORE_CONTEXTS = ("runtime_zero",)
EXPANDED_CONTEXTS = (
    "runtime_zero",
    "enable_false",
    "enable_true_mask_ones",
    "guard_positive",
    "guard_negative",
    "lane0_issuer",
    "derived_producers",
    "commit_completion",
)


def semantic_scale_vector(case: Case) -> str | None:
    """Normalize only aliases that are equivalent without inspecting idesc.K."""

    if case.kind == "mxf8f6f4" and case.scale_vector in (
        None,
        "scale_vec::1X",
        "block32",
    ):
        return "scale_vec::1X"
    if case.kind == "mxf4" and case.scale_vector is None:
        return "block32"
    return case.scale_vector


def normalized_steps(case: Case) -> list[dict]:
    default_buffer = "b0" if case.variant.startswith("mma.ws") else "a"
    return [
        asdict(
            step
            if step.collector_op is not None
            else Step("discard", default_buffer, step.ashift)
        )
        for step in case.steps
    ]


def semantic_form(case: Case) -> dict:
    return {
        "variant": case.variant,
        "cta_group": case.cta_group,
        "kind": case.kind,
        "a_form": case.a_form,
        "scale_vector_semantics": semantic_scale_vector(case),
        "scale_input_d": case.scale_input_d,
        "zero_column_mask": case.zero_column_mask,
        "collector_steps": normalized_steps(case),
    }


def static_context_assignment(case: Case) -> dict:
    mask_present = not (
        case.variant.startswith("mma.ws") or case.kind in BLOCK_SCALE_VECTORS
    )
    assignment = {
        "enable_input_d": {
            "producer": "runtime_parameter_ne_zero",
            "known_value": None,
        },
        "disable_output_lane": (
            {"producer": "constant", "word_value": "0x00000000"}
            if mask_present
            else {"mode": "not_present"}
        ),
        "target_guard": {"mode": "unpredicated"},
        "issuer": {"mode": "current_thread"},
        "operand_producers": {"mode": "direct_parameters"},
        "completion": {"mode": "none"},
    }
    if case.context_profile == "enable_false":
        assignment["enable_input_d"] = {
            "producer": "compile_time_predicate",
            "known_value": False,
        }
    elif case.context_profile == "enable_true_mask_ones":
        assignment["enable_input_d"] = {
            "producer": "compile_time_predicate",
            "known_value": True,
        }
        if mask_present:
            assignment["disable_output_lane"] = {
                "producer": "constant",
                "word_value": "0xffffffff",
            }
    elif case.context_profile == "guard_positive":
        assignment["target_guard"] = {
            "mode": "predicate",
            "polarity": "positive",
            "producer": "runtime_parameter_ne_zero",
        }
    elif case.context_profile == "guard_negative":
        assignment["target_guard"] = {
            "mode": "predicate",
            "polarity": "negative",
            "producer": "runtime_parameter_ne_zero",
        }
    elif case.context_profile == "lane0_issuer":
        assignment["issuer"] = {
            "mode": "lane_zero_branch",
            "producer": "%laneid",
        }
    elif case.context_profile == "derived_producers":
        assignment["operand_producers"] = {
            "mode": "identity_arithmetic_chain",
            "operations": ["add_zero", "xor_zero", "or_zero"],
        }
    elif case.context_profile == "commit_completion":
        assignment["completion"] = {
            "mode": "tcgen05_commit",
            "mechanism": "mbarrier::arrive::one",
            "cta_group": case.cta_group,
        }
    return assignment


def source_variant(case: Case) -> dict:
    return {
        "collector_spelling": case.collector_mode,
        "emitted_steps": [asdict(step) for step in case.steps],
        "scale_vector_spelling": (
            "omitted" if case.scale_vector is None else case.scale_vector
        ),
        "kernel_template": "thor_tcgen05_mma_v2",
    }


def source_identity(case: Case) -> dict:
    return {
        "semantic_form": semantic_form(case),
        "static_context_assignment": static_context_assignment(case),
        "source_variant": source_variant(case),
    }


def a_collector_modes(
    a_form: str, *, allow_ashift: bool
) -> tuple[tuple[str, tuple[Step, ...]], ...]:
    common = (
        ("implicit_discard", (Step(),)),
        ("explicit_discard", (Step("discard", "a"),)),
        ("fill", (Step("fill", "a"),)),
        ("fill_then_use", (Step("fill", "a"), Step("use", "a"))),
        ("fill_then_lastuse", (Step("fill", "a"), Step("lastuse", "a"))),
    )
    if a_form == "smem_descriptor" or not allow_ashift:
        return common
    return common + (
        ("ashift_implicit_discard", (Step(ashift=True),)),
        ("ashift_explicit_discard", (Step("discard", "a", True),)),
        (
            "fill_then_ashift_lastuse",
            (Step("fill", "a"), Step("lastuse", "a", True)),
        ),
    )


def b_collector_modes() -> tuple[tuple[str, tuple[Step, ...]], ...]:
    result: list[tuple[str, tuple[Step, ...]]] = [
        ("implicit_b0_discard", (Step(),))
    ]
    for buffer_index in range(4):
        buffer_name = f"b{buffer_index}"
        result.extend(
            (
                (
                    f"{buffer_name}_explicit_discard",
                    (Step("discard", buffer_name),),
                ),
                (f"{buffer_name}_fill", (Step("fill", buffer_name),)),
                (
                    f"{buffer_name}_fill_then_use",
                    (Step("fill", buffer_name), Step("use", buffer_name)),
                ),
                (
                    f"{buffer_name}_fill_then_lastuse",
                    (Step("fill", buffer_name), Step("lastuse", buffer_name)),
                ),
            )
        )
    return tuple(result)


def enumerate_source_forms() -> list[Case]:
    cases: list[Case] = []

    # mma / mma.sp, non-block-scaled.
    for variant in ("mma", "mma.sp"):
        for cta_group in (1, 2):
            for a_form in ("smem_descriptor", "tmem_address"):
                for kind, scale_values in STANDARD_SCALE_INPUTS.items():
                    for scale_input_d in scale_values:
                        for collector_mode, steps in a_collector_modes(
                            a_form, allow_ashift=True
                        ):
                            cases.append(
                                Case(
                                    variant=variant,
                                    cta_group=cta_group,
                                    kind=kind,
                                    a_form=a_form,
                                    scale_vector=None,
                                    scale_input_d=scale_input_d,
                                    zero_column_mask=False,
                                    collector_mode=collector_mode,
                                    steps=steps,
                                    context_profile="",
                                )
                            )

    # mma / mma.sp, block-scaled.
    for variant in ("mma", "mma.sp"):
        for cta_group in (1, 2):
            for a_form in ("smem_descriptor", "tmem_address"):
                for kind, scale_vectors in BLOCK_SCALE_VECTORS.items():
                    for scale_vector in scale_vectors:
                        for collector_mode, steps in a_collector_modes(
                            a_form, allow_ashift=False
                        ):
                            cases.append(
                                Case(
                                    variant=variant,
                                    cta_group=cta_group,
                                    kind=kind,
                                    a_form=a_form,
                                    scale_vector=scale_vector,
                                    scale_input_d=None,
                                    zero_column_mask=False,
                                    collector_mode=collector_mode,
                                    steps=steps,
                                    context_profile="",
                                )
                            )

    # Weight-stationary forms use CTA group 1 and B collector buffers.
    for variant in ("mma.ws", "mma.ws.sp"):
        for a_form in ("smem_descriptor", "tmem_address"):
            for kind in ("f16", "tf32", "f8f6f4", "i8"):
                for zero_column_mask in (False, True):
                    for collector_mode, steps in b_collector_modes():
                        cases.append(
                            Case(
                                variant=variant,
                                cta_group=1,
                                kind=kind,
                                a_form=a_form,
                                scale_vector=None,
                                scale_input_d=None,
                                zero_column_mask=zero_column_mask,
                                collector_mode=collector_mode,
                                steps=steps,
                                context_profile="",
                            )
                        )
    return cases


def expand_contexts(cases: list[Case], mode: str) -> list[Case]:
    profiles = CORE_CONTEXTS if mode == "syntax" else EXPANDED_CONTEXTS
    return [
        Case(**{**asdict(case), "steps": case.steps, "context_profile": profile})
        for case in cases
        for profile in profiles
    ]


def qualifier(step: Step) -> str:
    result = ".ashift" if step.ashift else ""
    if step.collector_op is not None:
        result += f".collector::{step.collector_buffer}::{step.collector_op}"
    return result


def instruction(case: Case, step: Step) -> str:
    opcode = f"tcgen05.{case.variant}.cta_group::{case.cta_group}.kind::{case.kind}"
    if case.scale_vector is not None or case.kind in BLOCK_SCALE_VECTORS:
        opcode += ".block_scale"
        if case.scale_vector is not None:
            opcode += f".{case.scale_vector}"
    opcode += qualifier(step)

    a_operand = "%desc_a" if case.a_form == "smem_descriptor" else "[%a_tmem]"
    operands = ["[%d_tmem]", a_operand, "%desc_b"]
    if case.variant.endswith(".sp"):
        operands.append("[%meta_tmem]")
    operands.append("%idesc")

    if case.kind in BLOCK_SCALE_VECTORS:
        operands.extend(("[%scale_a_tmem]", "[%scale_b_tmem]", "%enable"))
    elif case.variant.startswith("mma.ws"):
        operands.append("%enable")
        if case.zero_column_mask:
            operands.append("%zero_mask_desc")
    else:
        mask_count = 4 if case.cta_group == 1 else 8
        operands.append("{" + ", ".join(f"%mask{i}" for i in range(mask_count)) + "}")
        operands.append("%enable")
        if case.scale_input_d is not None:
            operands.append(str(case.scale_input_d))

    guard = ""
    if case.context_profile == "guard_positive":
        guard = "@%guard "
    elif case.context_profile == "guard_negative":
        guard = "@!%guard "
    return f"{guard}{opcode} " + ", ".join(operands) + ";"


def render_kernel(case: Case, ordinal: int) -> str:
    symbol = f"thor_tcgen05_mma_{ordinal:06d}"
    mask_count = 0 if case.variant.startswith("mma.ws") or case.kind in BLOCK_SCALE_VECTORS else (
        4 if case.cta_group == 1 else 8
    )
    lines = [
        f"// CASE_BEGIN {ordinal:06d}",
        "// semantic_form "
        + json.dumps(semantic_form(case), sort_keys=True, separators=(",", ":")),
        "// static_context_assignment "
        + json.dumps(
            static_context_assignment(case),
            sort_keys=True,
            separators=(",", ":"),
        ),
        "// source_variant "
        + json.dumps(source_variant(case), sort_keys=True, separators=(",", ":")),
        f".visible .entry {symbol}(",
        "    .param .u32 p_d_tmem,",
        "    .param .u32 p_a_tmem,",
        "    .param .u64 p_desc_a,",
        "    .param .u64 p_desc_b,",
        "    .param .u32 p_meta_tmem,",
        "    .param .u32 p_idesc,",
        "    .param .u32 p_scale_a_tmem,",
        "    .param .u32 p_scale_b_tmem,",
        "    .param .u64 p_zero_mask_desc,",
        "    .param .u32 p_enable,",
        "    .param .u32 p_guard,",
        "    .param .u64 p_mbar",
        ")",
        "{",
        "    .reg .b32 %d_tmem, %a_tmem, %meta_tmem, %idesc;",
        "    .reg .b32 %scale_a_tmem, %scale_b_tmem, %enable_u32, %guard_u32;",
        "    .reg .b64 %desc_a, %desc_b, %zero_mask_desc, %mbar;",
        "    .reg .pred %enable, %guard, %issuer;",
    ]
    if mask_count:
        lines.append(f"    .reg .b32 %mask<{mask_count}>;")
    if case.context_profile == "lane0_issuer":
        lines.append("    .reg .u32 %lane;")

    lines.extend(
        (
            "    ld.param.b32 %d_tmem, [p_d_tmem];",
            "    ld.param.b32 %a_tmem, [p_a_tmem];",
            "    ld.param.b64 %desc_a, [p_desc_a];",
            "    ld.param.b64 %desc_b, [p_desc_b];",
            "    ld.param.b32 %meta_tmem, [p_meta_tmem];",
            "    ld.param.b32 %idesc, [p_idesc];",
            "    ld.param.b32 %scale_a_tmem, [p_scale_a_tmem];",
            "    ld.param.b32 %scale_b_tmem, [p_scale_b_tmem];",
            "    ld.param.b64 %zero_mask_desc, [p_zero_mask_desc];",
            "    ld.param.b32 %enable_u32, [p_enable];",
            "    ld.param.b32 %guard_u32, [p_guard];",
            "    ld.param.b64 %mbar, [p_mbar];",
        )
    )

    if case.context_profile == "derived_producers":
        lines.extend(
            (
                "    add.u32 %d_tmem, %d_tmem, 0;",
                "    add.u32 %a_tmem, %a_tmem, 0;",
                "    xor.b64 %desc_a, %desc_a, 0;",
                "    or.b64 %desc_b, %desc_b, 0;",
                "    xor.b32 %idesc, %idesc, 0;",
            )
        )

    if case.context_profile == "enable_false":
        lines.append("    setp.ne.u32 %enable, 0, 0;")
    elif case.context_profile == "enable_true_mask_ones":
        lines.append("    setp.eq.u32 %enable, 0, 0;")
    else:
        lines.append("    setp.ne.u32 %enable, %enable_u32, 0;")
    lines.append("    setp.ne.u32 %guard, %guard_u32, 0;")

    mask_value = (
        "0xffffffff"
        if case.context_profile == "enable_true_mask_ones"
        else "0"
    )
    for index in range(mask_count):
        lines.append(f"    mov.b32 %mask{index}, {mask_value};")

    if case.context_profile == "lane0_issuer":
        lines.extend(
            (
                "    mov.u32 %lane, %laneid;",
                "    setp.eq.u32 %issuer, %lane, 0;",
                f"    @!%issuer bra CASE_END_{ordinal:06d};",
            )
        )

    lines.append("    // TARGET_PATTERN_BEGIN")
    for step_index, step in enumerate(case.steps):
        lines.append(f"    // target_occurrence {step_index}")
        lines.append(f"    {instruction(case, step)}")
    if case.context_profile == "commit_completion":
        lines.append(
            f"    tcgen05.commit.cta_group::{case.cta_group}."
            "mbarrier::arrive::one.b64 [%mbar];"
        )
    lines.append("    // TARGET_PATTERN_END")

    if case.context_profile == "lane0_issuer":
        lines.append(f"CASE_END_{ordinal:06d}:")
    lines.extend(("    ret;", "}", f"// CASE_END {ordinal:06d}", ""))
    return "\n".join(lines)


def write_suite(output: Path, cases: list[Case], shard_size: int, mode: str) -> None:
    output = reset_owned_directory(
        output, owner="thor_tcgen05_mma_generated", protected=(ROOT,)
    )

    manifest_rows = []
    for ordinal, case in enumerate(cases, start=1):
        shard = (ordinal - 1) // shard_size
        sf = semantic_form(case)
        context = static_context_assignment(case)
        variant = source_variant(case)
        semantic_form_id = stable_hash(sf)
        static_context_id = stable_hash(context)
        source_variant_id = stable_hash(variant)
        implementation_id = stable_hash(
            {
                "semantic_form_id": semantic_form_id,
                "static_context_id": static_context_id,
                "source_variant_id": source_variant_id,
            }
        )
        manifest_rows.append(
            {
                "case_label": f"THOR_MMA_{ordinal:06d}",
                "source_implementation_id": implementation_id,
                "semantic_form_id": semantic_form_id,
                "static_context_id": static_context_id,
                "source_variant_id": source_variant_id,
                "kernel": f"thor_tcgen05_mma_{ordinal:06d}",
                "source_shard": f"thor_tcgen05_mma_{shard:04d}.ptx",
                "target_occurrence_count": len(case.steps),
                "target_instructions": [
                    instruction(case, step) for step in case.steps
                ],
                "context_profile_label": case.context_profile,
                "semantic_form": sf,
                "static_context_assignment": context,
                "source_variant": variant,
                "validation_scope": "STATIC_ASSEMBLY_ONLY",
            }
        )

    shard_count = (len(cases) + shard_size - 1) // shard_size
    for shard in range(shard_count):
        begin = shard * shard_size
        end = min(begin + shard_size, len(cases))
        source = [
            ".version 9.0",
            ".target sm_110a",
            ".address_size 64",
            f'.file 1 "thor_tcgen05_mma_{shard:04d}.ptx"',
            "",
        ]
        source.extend(
            render_kernel(cases[index], index + 1)
            for index in range(begin, end)
        )
        (output / f"thor_tcgen05_mma_{shard:04d}.ptx").write_text(
            "\n".join(source), encoding="utf-8"
        )

    with (output / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for row in manifest_rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    semantic_ids = {row["semantic_form_id"] for row in manifest_rows}
    static_context_ids = {row["static_context_id"] for row in manifest_rows}
    logical_design_ids = {
        stable_hash(
            {
                "semantic_form_id": row["semantic_form_id"],
                "static_context_id": row["static_context_id"],
            }
        )
        for row in manifest_rows
    }
    source_variant_ids = {row["source_variant_id"] for row in manifest_rows}
    summary = {
        "schema_version": "thor_tcgen05_mma_generator_v2",
        "ptx_isa": "9.0",
        "ptx_target": "sm_110a",
        "device_family": "NVIDIA Thor / compute capability 11.0",
        "generation_mode": mode,
        "source_implementation_count": len(cases),
        "semantic_form_count": len(semantic_ids),
        "static_context_count": len(static_context_ids),
        "logical_design_count": len(logical_design_ids),
        "source_variant_count": len(source_variant_ids),
        "target_occurrence_count": sum(len(case.steps) for case in cases),
        "source_shard_count": shard_count,
        "shard_size": shard_size,
        "coverage": {
            "surface_form_model": "constrained exhaustive",
            "context_model": "baseline" if mode == "syntax" else "bounded exhaustive profiles",
            "descriptor_bitfields": "runtime unknown; not enumerated",
            "runtime_semantics": "not validated",
        },
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    validation = validate_directory(output)
    print(
        f"generated {len(cases)} source implementations / "
        f"{len(semantic_ids)} semantic forms / "
        f"{len(logical_design_ids)} logical designs / "
        f"{summary['target_occurrence_count']} occurrences / {shard_count} shards; "
        f"source validation {validation['validation_status']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("syntax", "expanded"),
        default="syntax",
        help="syntax: exhaustive qualifier forms; expanded: cross with 8 static contexts",
    )
    parser.add_argument("--shard-size", type=int, default=64)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "generated",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.shard_size < 1:
        raise SystemExit("--shard-size must be positive")
    source_forms = enumerate_source_forms()
    cases = expand_contexts(source_forms, args.mode)
    write_suite(args.output, cases, args.shard_size, args.mode)


if __name__ == "__main__":
    main()

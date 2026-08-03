#!/usr/bin/env python3
"""Generate a constrained tcgen05.mma matrix for NVIDIA Thor.

The default ``syntax`` mode exhaustively enumerates the legal PTX 9.0 surface
forms declared below. ``expanded`` crosses the same forms with bounded static
context profiles. Descriptor values are treated as opaque register operands.
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
    "lane31_issuer",
    "dynamic_lane_issuer",
    "thread0_issuer",
    "compound_predicated_issuer",
    "derived_producers",
    "nonidentity_producers",
    "branched_producers",
    "global_load_producers",
    "commit_completion",
)

BRANCH_ISSUER_PROFILES = {
    "lane0_issuer",
    "lane31_issuer",
    "dynamic_lane_issuer",
    "thread0_issuer",
}

PREDICATE_PRESSURE_PROFILES = {
    "predicate_pressure_1": 1,
    "predicate_pressure_2": 2,
    "predicate_pressure_3": 3,
    "predicate_pressure_4": 4,
    "predicate_pressure_5": 5,
    "predicate_pressure_6": 6,
}

ENCODING_PROBE_CONTEXTS = (
    "predicate_index_up0",
    *PREDICATE_PRESSURE_PROFILES,
    "idesc_pair_pressure",
)


def predicate_hold_count(case: Case) -> int:
    if case.context_profile == "enable_index_sweep":
        return 7
    return PREDICATE_PRESSURE_PROFILES.get(case.context_profile, 0)


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
    elif case.context_profile == "predicate_index_up0":
        assignment["enable_input_d"] = {
            "producer": "compile_time_predicate",
            "known_value": True,
        }
        assignment["target_guard"] = {
            "mode": "predicate_index_probe",
            "polarity": "positive",
            "producer": "runtime_parameter_ne_zero",
            "expected_allocator_goal": "UP0",
        }
    elif case.context_profile == "lane0_issuer":
        assignment["issuer"] = {
            "mode": "lane_zero_branch",
            "producer": "%laneid",
        }
    elif case.context_profile == "lane31_issuer":
        assignment["issuer"] = {
            "mode": "lane_immediate_branch",
            "producer": "%laneid",
            "lane": 31,
        }
    elif case.context_profile == "dynamic_lane_issuer":
        assignment["issuer"] = {
            "mode": "lane_parameter_branch",
            "producer": "%laneid",
            "lane_parameter": "p_issuer_lane",
        }
    elif case.context_profile == "thread0_issuer":
        assignment["issuer"] = {
            "mode": "cta_thread_zero_branch",
            "producer": "%tid.x",
        }
    elif case.context_profile == "compound_predicated_issuer":
        assignment["issuer"] = {
            "mode": "lane_zero_and_parameter_predicate",
            "producers": ["%laneid", "p_guard"],
            "target_lowering": "direct_predication",
        }
    elif case.context_profile in PREDICATE_PRESSURE_PROFILES:
        assignment["target_guard"] = {
            "mode": "predicate_index_pressure",
            "polarity": "positive",
            "producer": "runtime_parameter_ne_zero",
            "live_uniform_predicates_across_target": PREDICATE_PRESSURE_PROFILES[
                case.context_profile
            ],
        }
    elif case.context_profile == "enable_index_sweep":
        assignment["enable_input_d"] = {
            "producer": "predicate_index_sweep",
            "virtual_predicates": [f"hold{index}" for index in range(7)],
            "target_occurrence_mapping": "occurrence i uses hold[i]",
        }
    elif case.context_profile == "derived_producers":
        assignment["operand_producers"] = {
            "mode": "identity_arithmetic_chain",
            "operations": ["add_zero", "xor_zero", "or_zero"],
            "covered_inputs": [
                "d_tmem",
                "a_tmem",
                "desc_a",
                "desc_b",
                "meta_tmem",
                "idesc",
                "scale_a_tmem",
                "scale_b_tmem",
                "zero_mask_desc",
                "enable",
                "guard",
                "mbar",
            ],
        }
    elif case.context_profile == "nonidentity_producers":
        assignment["operand_producers"] = {
            "mode": "runtime_delta_arithmetic_chain",
            "delta_parameter": "p_producer_delta",
            "operations": ["add_delta", "xor_delta"],
            "covered_inputs": [
                "d_tmem",
                "a_tmem",
                "desc_a",
                "desc_b",
                "meta_tmem",
                "idesc",
                "scale_a_tmem",
                "scale_b_tmem",
                "zero_mask_desc",
                "enable",
                "guard",
                "mbar",
            ],
        }
    elif case.context_profile == "branched_producers":
        assignment["operand_producers"] = {
            "mode": "branch_selected_runtime_delta",
            "selector": "p_guard_ne_zero",
            "delta_parameter": "p_producer_delta",
            "control_flow": "conditional_basic_block",
        }
    elif case.context_profile == "global_load_producers":
        assignment["operand_producers"] = {
            "mode": "global_memory_loads",
            "base_parameter": "p_source_ptr",
            "addressing": "fixed_role_offsets",
        }
    elif case.context_profile == "idesc_pair_pressure":
        assignment["operand_producers"] = {
            "mode": "uniform_register_pressure_across_target",
            "live_uniform_64bit_values": 8,
            "purpose": "attempt to separate auxiliary and idesc physical allocation",
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
        "kernel_template": "thor_tcgen05_mma_v4",
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
    expanded = [
        Case(**{**asdict(case), "steps": case.steps, "context_profile": profile})
        for case in cases
        for profile in profiles
    ]
    if mode == "expanded":
        representative = next(
            case
            for case in cases
            if case.variant == "mma"
            and case.cta_group == 1
            and case.kind == "f16"
            and case.a_form == "smem_descriptor"
            and case.collector_mode == "fill_then_use"
        )
        expanded.extend(
            Case(
                **{
                    **asdict(representative),
                    "steps": representative.steps,
                    "context_profile": profile,
                }
            )
            for profile in ENCODING_PROBE_CONTEXTS
        )
        enable_sweep_case = Case(
            **{
                **asdict(representative),
                "collector_mode": "encoding_enable_index_sweep",
                "steps": tuple(Step() for _ in range(7)),
                "context_profile": "",
            }
        )
        expanded.extend(
            Case(
                **{
                    **asdict(enable_sweep_case),
                    "steps": enable_sweep_case.steps,
                    "context_profile": profile,
                }
            )
            for profile in ("runtime_zero", "enable_index_sweep")
        )
    return expanded


def qualifier(step: Step) -> str:
    result = ".ashift" if step.ashift else ""
    if step.collector_op is not None:
        result += f".collector::{step.collector_buffer}::{step.collector_op}"
    return result


def instruction(case: Case, step: Step, step_index: int = 0) -> str:
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

    enable_operand = "%enable"
    if case.context_profile == "enable_index_sweep":
        enable_operand = f"%hold{step_index}"
    if case.kind in BLOCK_SCALE_VECTORS:
        operands.extend(("[%scale_a_tmem]", "[%scale_b_tmem]", enable_operand))
    elif case.variant.startswith("mma.ws"):
        operands.append(enable_operand)
        if case.zero_column_mask:
            operands.append("%zero_mask_desc")
    else:
        mask_count = 4 if case.cta_group == 1 else 8
        operands.append("{" + ", ".join(f"%mask{i}" for i in range(mask_count)) + "}")
        operands.append(enable_operand)
        if case.scale_input_d is not None:
            operands.append(str(case.scale_input_d))

    guard = ""
    if case.context_profile == "guard_positive":
        guard = "@%guard "
    elif case.context_profile == "guard_negative":
        guard = "@!%guard "
    elif case.context_profile == "compound_predicated_issuer":
        guard = "@%issuer "
    elif case.context_profile == "predicate_index_up0":
        guard = "@%guard "
    elif case.context_profile in PREDICATE_PRESSURE_PROFILES:
        guard = (
            f"@%hold{PREDICATE_PRESSURE_PROFILES[case.context_profile] - 1} "
        )
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
        "    .param .u64 p_mbar,",
        "    .param .u32 p_issuer_lane,",
        "    .param .u32 p_producer_delta,",
        "    .param .u64 p_source_ptr",
        ")",
        "{",
        "    .reg .b32 %d_tmem, %a_tmem, %meta_tmem, %idesc;",
        "    .reg .b32 %scale_a_tmem, %scale_b_tmem, %enable_u32, %guard_u32;",
        "    .reg .b32 %issuer_lane_u32, %producer_delta;",
        "    .reg .b64 %desc_a, %desc_b, %zero_mask_desc, %mbar, %source_ptr, %producer_delta64;",
        "    .reg .pred %enable, %guard, %issuer, %issuer_guard, %producer_select, %indexed_guard;",
    ]
    if mask_count:
        lines.append(f"    .reg .b32 %mask<{mask_count}>;")
    if case.context_profile in {"lane0_issuer", "lane31_issuer", "dynamic_lane_issuer", "compound_predicated_issuer"}:
        lines.append("    .reg .u32 %lane;")
    if case.context_profile == "thread0_issuer":
        lines.append("    .reg .u32 %thread_index;")
    if case.context_profile == "branched_producers":
        lines.extend(
            (
                "    .reg .b32 %d_alt, %a_alt, %meta_alt, %idesc_alt;",
                "    .reg .b32 %scale_a_alt, %scale_b_alt, %enable_alt, %guard_alt;",
                "    .reg .b64 %desc_a_alt, %desc_b_alt, %zero_mask_alt, %mbar_alt;",
            )
        )
    if predicate_hold_count(case):
        lines.append("    .reg .pred %hold<7>;")
    if case.context_profile == "idesc_pair_pressure":
        lines.append("    .reg .b64 %idesc_pressure<8>;")

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
            "    ld.param.b32 %issuer_lane_u32, [p_issuer_lane];",
            "    ld.param.b32 %producer_delta, [p_producer_delta];",
            "    ld.param.b64 %source_ptr, [p_source_ptr];",
        )
    )

    if case.context_profile == "derived_producers":
        lines.extend(
            (
                "    add.u32 %d_tmem, %d_tmem, 0;",
                "    add.u32 %a_tmem, %a_tmem, 0;",
                "    xor.b64 %desc_a, %desc_a, 0;",
                "    or.b64 %desc_b, %desc_b, 0;",
                "    add.u32 %meta_tmem, %meta_tmem, 0;",
                "    xor.b32 %idesc, %idesc, 0;",
                "    add.u32 %scale_a_tmem, %scale_a_tmem, 0;",
                "    add.u32 %scale_b_tmem, %scale_b_tmem, 0;",
                "    xor.b64 %zero_mask_desc, %zero_mask_desc, 0;",
                "    or.b32 %enable_u32, %enable_u32, 0;",
                "    xor.b32 %guard_u32, %guard_u32, 0;",
                "    add.u64 %mbar, %mbar, 0;",
            )
        )
    elif case.context_profile in {"nonidentity_producers", "branched_producers"}:
        lines.append("    cvt.u64.u32 %producer_delta64, %producer_delta;")
        if case.context_profile == "nonidentity_producers":
            lines.extend(
                (
                    "    add.u32 %d_tmem, %d_tmem, %producer_delta;",
                    "    add.u32 %a_tmem, %a_tmem, %producer_delta;",
                    "    xor.b64 %desc_a, %desc_a, %producer_delta64;",
                    "    xor.b64 %desc_b, %desc_b, %producer_delta64;",
                    "    add.u32 %meta_tmem, %meta_tmem, %producer_delta;",
                    "    xor.b32 %idesc, %idesc, %producer_delta;",
                    "    add.u32 %scale_a_tmem, %scale_a_tmem, %producer_delta;",
                    "    add.u32 %scale_b_tmem, %scale_b_tmem, %producer_delta;",
                    "    xor.b64 %zero_mask_desc, %zero_mask_desc, %producer_delta64;",
                    "    xor.b32 %enable_u32, %enable_u32, %producer_delta;",
                    "    xor.b32 %guard_u32, %guard_u32, %producer_delta;",
                    "    add.u64 %mbar, %mbar, %producer_delta64;",
                )
            )
        else:
            lines.extend(
                (
                    "    add.u32 %d_alt, %d_tmem, %producer_delta;",
                    "    add.u32 %a_alt, %a_tmem, %producer_delta;",
                    "    xor.b64 %desc_a_alt, %desc_a, %producer_delta64;",
                    "    xor.b64 %desc_b_alt, %desc_b, %producer_delta64;",
                    "    add.u32 %meta_alt, %meta_tmem, %producer_delta;",
                    "    xor.b32 %idesc_alt, %idesc, %producer_delta;",
                    "    add.u32 %scale_a_alt, %scale_a_tmem, %producer_delta;",
                    "    add.u32 %scale_b_alt, %scale_b_tmem, %producer_delta;",
                    "    xor.b64 %zero_mask_alt, %zero_mask_desc, %producer_delta64;",
                    "    xor.b32 %enable_alt, %enable_u32, %producer_delta;",
                    "    xor.b32 %guard_alt, %guard_u32, %producer_delta;",
                    "    add.u64 %mbar_alt, %mbar, %producer_delta64;",
                    "    setp.ne.u32 %producer_select, %guard_u32, 0;",
                    f"    @!%producer_select bra PRODUCER_DONE_{ordinal:06d};",
                    "    mov.b32 %d_tmem, %d_alt;",
                    "    mov.b32 %a_tmem, %a_alt;",
                    "    mov.b64 %desc_a, %desc_a_alt;",
                    "    mov.b64 %desc_b, %desc_b_alt;",
                    "    mov.b32 %meta_tmem, %meta_alt;",
                    "    mov.b32 %idesc, %idesc_alt;",
                    "    mov.b32 %scale_a_tmem, %scale_a_alt;",
                    "    mov.b32 %scale_b_tmem, %scale_b_alt;",
                    "    mov.b64 %zero_mask_desc, %zero_mask_alt;",
                    "    mov.b32 %enable_u32, %enable_alt;",
                    "    mov.b32 %guard_u32, %guard_alt;",
                    "    mov.b64 %mbar, %mbar_alt;",
                    f"PRODUCER_DONE_{ordinal:06d}:",
                )
            )
    elif case.context_profile == "global_load_producers":
        lines.extend(
            (
                "    ld.global.u32 %d_tmem, [%source_ptr+0];",
                "    ld.global.u32 %a_tmem, [%source_ptr+4];",
                "    ld.global.u64 %desc_a, [%source_ptr+8];",
                "    ld.global.u64 %desc_b, [%source_ptr+16];",
                "    ld.global.u32 %meta_tmem, [%source_ptr+24];",
                "    ld.global.u32 %idesc, [%source_ptr+28];",
                "    ld.global.u32 %scale_a_tmem, [%source_ptr+32];",
                "    ld.global.u32 %scale_b_tmem, [%source_ptr+36];",
                "    ld.global.u64 %zero_mask_desc, [%source_ptr+40];",
                "    ld.global.u32 %enable_u32, [%source_ptr+48];",
                "    ld.global.u32 %guard_u32, [%source_ptr+52];",
                "    ld.global.u64 %mbar, [%source_ptr+56];",
            )
        )

    if case.context_profile == "idesc_pair_pressure":
        for index in range(8):
            lines.append(
                f"    add.u64 %idesc_pressure{index}, %mbar, {16 * (index + 1)};"
            )

    if case.context_profile == "enable_false":
        lines.append("    setp.ne.u32 %enable, 0, 0;")
    elif case.context_profile in {"enable_true_mask_ones", "predicate_index_up0"}:
        lines.append("    setp.eq.u32 %enable, 0, 0;")
    else:
        lines.append("    setp.ne.u32 %enable, %enable_u32, 0;")
    lines.append("    setp.ne.u32 %guard, %guard_u32, 0;")

    if predicate_hold_count(case):
        hold_count = predicate_hold_count(case)
        hold_sources = (
            "%producer_delta",
            "%issuer_lane_u32",
            "%d_tmem",
            "%a_tmem",
            "%meta_tmem",
            "%scale_a_tmem",
            "%scale_b_tmem",
        )
        for index in range(hold_count):
            lines.append(
                f"    setp.ne.u32 %hold{index}, {hold_sources[index]}, 0;"
            )

    if case.context_profile == "idesc_pair_pressure":
        for index in range(8):
            lines.append(
                f"    tcgen05.commit.cta_group::{case.cta_group}."
                f"mbarrier::arrive::one.b64 [%idesc_pressure{index}];"
            )

    mask_value = (
        "0xffffffff"
        if case.context_profile == "enable_true_mask_ones"
        else "0"
    )
    for index in range(mask_count):
        lines.append(f"    mov.b32 %mask{index}, {mask_value};")

    if case.context_profile in {"lane0_issuer", "lane31_issuer", "dynamic_lane_issuer"}:
        compare_value = "0" if case.context_profile == "lane0_issuer" else "31" if case.context_profile == "lane31_issuer" else "%issuer_lane_u32"
        lines.extend(
            (
                "    mov.u32 %lane, %laneid;",
                f"    setp.eq.u32 %issuer, %lane, {compare_value};",
                f"    @!%issuer bra CASE_END_{ordinal:06d};",
            )
        )
    elif case.context_profile == "thread0_issuer":
        lines.extend(
            (
                "    mov.u32 %thread_index, %tid.x;",
                "    setp.eq.u32 %issuer, %thread_index, 0;",
                f"    @!%issuer bra CASE_END_{ordinal:06d};",
            )
        )
    elif case.context_profile == "compound_predicated_issuer":
        lines.extend(
            (
                "    mov.u32 %lane, %laneid;",
                "    setp.eq.u32 %issuer, %lane, 0;",
                "    setp.ne.u32 %issuer_guard, %guard_u32, 0;",
                "    and.pred %issuer, %issuer, %issuer_guard;",
            )
        )

    if predicate_hold_count(case):
        hold_count = predicate_hold_count(case)
        for index in range(hold_count):
            lines.append(
                f"    @%hold{index} tcgen05.commit.cta_group::{case.cta_group}."
                "mbarrier::arrive::one.b64 [%mbar];"
            )
    lines.append("    // TARGET_PATTERN_BEGIN")
    for step_index, step in enumerate(case.steps):
        lines.append(f"    // target_occurrence {step_index}")
        lines.append(f"    {instruction(case, step, step_index)}")
    if case.context_profile == "commit_completion":
        lines.append(
            f"    tcgen05.commit.cta_group::{case.cta_group}."
            "mbarrier::arrive::one.b64 [%mbar];"
        )
    lines.append("    // TARGET_PATTERN_END")

    if predicate_hold_count(case):
        hold_count = predicate_hold_count(case)
        for index in range(hold_count):
            lines.append(
                f"    @%hold{index} tcgen05.commit.cta_group::{case.cta_group}."
                "mbarrier::arrive::one.b64 [%mbar];"
            )
    if case.context_profile == "idesc_pair_pressure":
        for index in range(8):
            lines.append(
                f"    tcgen05.commit.cta_group::{case.cta_group}."
                f"mbarrier::arrive::one.b64 [%idesc_pressure{index}];"
            )

    if case.context_profile in BRANCH_ISSUER_PROFILES:
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
                    instruction(case, step, step_index)
                    for step_index, step in enumerate(case.steps)
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
        "schema_version": "thor_tcgen05_mma_generator_v4",
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
            "descriptor_values": "opaque register operands",
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
        help="syntax: exhaustive qualifier forms; expanded: cross with bounded static contexts",
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

#!/usr/bin/env python3
"""Independent experiment definition for bar.warp.sync on Thor.

Pre-calibrated against ptxas V13.0.88 / nvdisasm V13.0.85 (`sm_110a`) with 50
scratch probes (see `16_megakernel_ctrl/实验设计.md`). Headline finding: this
opcode has two lowering regimes, not one.

- Unguarded (`bar.warp.sync mask;`): O0 always emits
  `WARPSYNC.COLLECTIVE Rn, target` + `ENDCOLLECTIVE`. O1-O3 eliminate it to
  zero instructions in *every* tested context (straight-line code, an
  if-convertible branch, a genuine data-dependent divergent loop with an
  atomic side effect, cross-lane shared-memory dependence, a predicated
  `exit` leaving a subset mask) because ptxas's own
  `BSSY.RECONVERGENT`/`BSYNC.RECONVERGENT` reconvergence bracket already
  proves the barrier redundant.
- Guarded (`@%p bar.warp.sync mask;`): materializes at O0-O3. A compile-time
  full mask (`0xffffffff` or its `-1` two's-complement spelling) lowers to
  the bare `WARPSYNC.ALL` form -- the same mnemonic `01_tcgen05` observed in
  the compiler-synthesized alloc/dealloc sequence. Any other mask (partial
  immediate, single-bit immediate, register, indirect-loaded register)
  lowers to `WARPSYNC Rn`. Two adjacent guarded syncs are not merged: they
  produce two independent `WARPSYNC.COLLECTIVE`/`BRA.DIV` blocks instead of
  the single-guard `@P0 BRA`+`WARPSYNC.ALL` shape.

`empty_target_allowed` therefore keys on `guard == "none"`: those
coordinates are legitimately D'-class (zero SASS at O1-O3) and only ever
show a positive `WARPSYNC` at O0; every `guard != "none"` coordinate must
show a `WARPSYNC*` occurrence at every optimization level, and a regression
there is a real failure, not a documented elimination.
"""

from suite_runtime import Case, Spec

MASK_TOKENS = {
    "full_imm": "0xffffffff",
    "partial_imm": "0x0000ffff",
    "zero_imm": "0x0",
    "single_bit_imm": "0x00000001",
    "neg_decimal_imm": "-1",
}

PARAMS_BASE = (".param .u64 p_out",)
PARAMS_REG = (".param .u32 p_mask", ".param .u64 p_out")
PARAMS_INDIRECT = (".param .u64 p_maskptr", ".param .u64 p_out")
SHARED_DECL = (".shared .align 4 .b32 smem_buf[32];",)


def _mask_operand(mask_kind: str) -> str:
    return "%mask" if mask_kind.startswith("reg") else MASK_TOKENS[mask_kind]


def _needs_shared(shared_context: str) -> bool:
    return shared_context != "none"


def _registers(mask_kind: str, guard: str, shared_context: str, variant: str) -> tuple[str, ...]:
    regs = [".reg .b32 %t0, %v;", ".reg .b64 %out;"]
    if _needs_shared(shared_context):
        regs.extend(SHARED_DECL)
    if guard != "none":
        regs.append(".reg .pred %p;")
    if mask_kind == "reg_direct":
        regs.append(".reg .b32 %mask;")
    elif mask_kind == "reg_indirect":
        regs.append(".reg .b32 %mask;")
        regs.append(".reg .b64 %maskptr;")
    if variant == "divergent_prefix":
        regs.append(".reg .b32 %i;")
        regs.append(".reg .pred %ploop;")
    if variant == "post_exit_subset":
        regs.append(".reg .pred %pexit;")
    return tuple(regs)


def _preparation(mask_kind: str, guard: str, shared_context: str, variant: str) -> tuple[str, ...]:
    prep = [
        "ld.param.b64 %out, [p_out];",
        "mov.u32 %t0, %tid.x;",
    ]
    if mask_kind == "reg_direct":
        prep.append("ld.param.u32 %mask, [p_mask];")
    elif mask_kind == "reg_indirect":
        prep.append("ld.param.b64 %maskptr, [p_maskptr];")
        prep.append("ld.global.u32 %mask, [%maskptr];")
    if variant == "post_exit_subset":
        prep.append("setp.ge.u32 %pexit, %t0, 16;")
        prep.append("@%pexit exit;")
    if variant == "divergent_prefix":
        prep.extend([
            "mov.u32 %v, 0;",
            "mov.u32 %i, 0;",
            "L_loop_body:",
            "setp.ge.u32 %ploop, %i, %t0;",
            "@%ploop bra L_loop_done;",
            "atom.global.add.u32 %v, [%out], %i;",
            "add.u32 %i, %i, 1;",
            "bra L_loop_body;",
            "L_loop_done:",
        ])
    prep.append("add.u32 %v, %t0, 1;")
    if guard != "none":
        prep.append("setp.lt.u32 %p, %t0, 16;")
    if shared_context in ("before", "both"):
        prep.append("st.shared.b32 [smem_buf], %t0;")
    return tuple(prep)


def _target(mask_kind: str, guard: str) -> tuple[str, ...]:
    operand = _mask_operand(mask_kind)
    prefix = "@%p " if guard != "none" else ""
    line = f"{prefix}bar.warp.sync {operand};"
    if guard == "double_predicated":
        return (line, line)
    return (line,)


def _observation(shared_context: str) -> tuple[str, ...]:
    obs = []
    if shared_context in ("after", "both"):
        obs.append("ld.shared.b32 %v, [smem_buf];")
    else:
        obs.append("add.u32 %v, %v, 1;")
    obs.append("st.global.b32 [%out], %v;")
    return tuple(obs)


def _params(mask_kind: str, variant: str) -> tuple[str, ...]:
    if mask_kind == "reg_direct":
        base = PARAMS_REG
    elif mask_kind == "reg_indirect":
        base = PARAMS_INDIRECT
    else:
        base = PARAMS_BASE
    if variant == "template_wide":
        return (".param .u32 p_pad0", *base[:-1], ".param .u64 p_pad1", base[-1], ".param .u32 p_pad2")
    return base


def _case(mask_kind: str, guard: str, shared_context: str = "both", variant: str = "baseline") -> Case:
    coords = {"mask_kind": mask_kind, "guard": guard, "shared_context": shared_context, "variant": variant}
    return Case(
        "",
        coords,
        parameters=_params(mask_kind, variant),
        registers=_registers(mask_kind, guard, shared_context, variant),
        preparation=_preparation(mask_kind, guard, shared_context, variant),
        target=_target(mask_kind, guard),
        observation=_observation(shared_context),
    )


def barwarpsync_cases() -> list[Case]:
    # Canonical matrix: mask_kind x guard, shared_context="both" (the realistic
    # usage: producer writes shared, sync, consumer reads a neighbor's slot).
    cases = []
    for mask_kind in ("full_imm", "partial_imm", "reg_direct"):
        for guard in ("none", "predicated"):
            cases.append(_case(mask_kind, guard))
    # P0-2 complement samples promoted into the positive matrix (see design
    # doc "两个被校准推翻的假设"): mask=0 and single-bit mask are legal.
    cases.append(_case("zero_imm", "none"))
    cases.append(_case("zero_imm", "predicated"))
    cases.append(_case("single_bit_imm", "predicated"))
    # Alternate spelling of the full mask (decimal two's-complement -1);
    # calibrated to compile identically to the 0xffffffff form.
    cases.append(_case("neg_decimal_imm", "none"))
    cases.append(_case("neg_decimal_imm", "predicated"))
    return cases


def barwarpsync_expanded() -> list[Case]:
    cases = barwarpsync_cases()

    # CTX.shared_placement (P0-1 / P0-3 bidirectional position check): sweep
    # shared-memory presence before/after the guarded sync for two mask
    # kinds. "both" is already the baseline above.
    for mask_kind in ("full_imm", "reg_direct"):
        for shared_context in ("none", "before", "after"):
            cases.append(_case(mask_kind, "predicated", shared_context=shared_context))
    # Same sweep unguarded, to show the D'-class elimination is independent
    # of shared-memory context (not just of mask kind).
    for shared_context in ("none", "before", "after"):
        cases.append(_case("partial_imm", "none", shared_context=shared_context))

    # CTX.double_guard: two adjacent guarded syncs are not merged/deduped
    # (calibrated: distinct WARPSYNC.COLLECTIVE/BRA.DIV shape, not a copy of
    # the single-guard WARPSYNC.ALL shape).
    cases.append(_case("full_imm", "double_predicated"))

    # CTX.mask_indirect (P1-2): mask loaded from global memory, not
    # foldable.
    cases.append(_case("reg_indirect", "predicated"))

    # CTX.divergent_prefix: guard survives even when preceded by a real
    # data-dependent divergent loop with an atomic side effect (rules out
    # "guard only matters in trivial straight-line code").
    cases.append(_case("full_imm", "predicated", variant="divergent_prefix"))

    # CTX.post_exit_subset: predicated exit shrinks the active set to
    # exactly the mask; both the unguarded (D'-class) and guarded (rescue)
    # forms are recorded.
    cases.append(_case("partial_imm", "none", variant="post_exit_subset"))
    cases.append(_case("partial_imm", "predicated", variant="post_exit_subset"))

    # CTX.template_wide (P1-1): padded/reordered kernel signature.
    cases.append(_case("full_imm", "predicated", variant="template_wide"))

    return cases


def barwarpsync_negative() -> list[Case]:
    def probe(coords: dict, target: str, reason: str, diagnostic: str) -> Case:
        return Case(
            "",
            coords,
            parameters=PARAMS_BASE,
            registers=(".reg .b32 %t0;", ".reg .b64 %out;"),
            preparation=("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;"),
            target=(target,),
            observation=("st.global.b32 [%out], %t0;",),
            expected="reject",
            reason=reason,
            expected_diagnostic=diagnostic,
        )

    diag = "Arguments mismatch for instruction 'bar.warp'"
    return [
        Case(
            "",
            {"probe": "mask_b64"},
            parameters=PARAMS_BASE,
            registers=(".reg .b32 %t0;", ".reg .b64 %out, %maskq;"),
            preparation=("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;", "mov.u64 %maskq, 0xffffffff;"),
            target=("bar.warp.sync %maskq;",),
            observation=("st.global.b32 [%out], %t0;",),
            expected="reject",
            reason="mask must be .b32, not .b64",
            expected_diagnostic=diag,
        ),
        Case(
            "",
            {"probe": "mask_f32"},
            parameters=PARAMS_BASE,
            registers=(".reg .b32 %t0;", ".reg .b64 %out;", ".reg .f32 %maskf;"),
            preparation=("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;", "mov.f32 %maskf, 1.0;"),
            target=("bar.warp.sync %maskf;",),
            observation=("st.global.b32 [%out], %t0;",),
            expected="reject",
            reason="mask must be an integer type, not .f32",
            expected_diagnostic=diag,
        ),
        probe({"probe": "missing_operand"}, "bar.warp.sync;", "mask operand is mandatory", diag),
        probe({"probe": "extra_operand"}, "bar.warp.sync 0xffffffff, 0x1;", "bar.warp.sync takes exactly one operand", diag),
        Case(
            "",
            {"probe": "mask_pred"},
            parameters=PARAMS_BASE,
            registers=(".reg .b32 %t0;", ".reg .b64 %out;", ".reg .pred %maskp;"),
            preparation=("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;", "setp.eq.u32 %maskp, %t0, 0;"),
            target=("bar.warp.sync %maskp;",),
            observation=("st.global.b32 [%out], %t0;",),
            expected="reject",
            reason="mask cannot be a .pred register",
            expected_diagnostic=diag,
        ),
        Case(
            "",
            {"probe": "mask_b16"},
            parameters=PARAMS_BASE,
            registers=(".reg .b32 %t0;", ".reg .b64 %out;", ".reg .b16 %maskh;"),
            preparation=("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;", "mov.u16 %maskh, 255;"),
            target=("bar.warp.sync %maskh;",),
            observation=("st.global.b32 [%out], %t0;",),
            expected="reject",
            reason="mask register is too narrow (.b16 < .b32)",
            expected_diagnostic=diag,
        ),
        # complement sampling outside the assumed-legal surface (P0-2): a
        # memory operand for the mask was assumed maybe-legal (mirroring
        # instructions that accept `[addr]` operands elsewhere in the ISA)
        # and is in fact rejected with the same diagnostic family.
        Case(
            "",
            {"probe": "mask_memory_operand"},
            parameters=(".param .u64 p_maskptr", ".param .u64 p_out"),
            registers=(".reg .b32 %t0;", ".reg .b64 %out, %maskptr;"),
            preparation=("ld.param.b64 %maskptr, [p_maskptr];", "ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;"),
            target=("bar.warp.sync [%maskptr];",),
            observation=("st.global.b32 [%out], %t0;",),
            expected="reject",
            reason="mask cannot be a memory operand",
            expected_diagnostic=diag,
        ),
    ]


FACTORS = (
    {"id": "SF.mask_kind", "levels": ["full_imm", "partial_imm", "zero_imm", "single_bit_imm", "neg_decimal_imm", "reg_direct", "reg_indirect"]},
    {"id": "SF.guard", "levels": ["none", "predicated", "double_predicated"]},
    {"id": "CTX.shared_context", "levels": ["none", "before", "after", "both"]},
    {"id": "CTX.variant", "levels": ["baseline", "template_wide", "divergent_prefix", "post_exit_subset"]},
)

SPEC = Spec(
    family="mega",
    opcode="bar_warp_sync",
    ptx_opcode="bar.warp.sync",
    target_patterns=("WARPSYNC",),
    factors=FACTORS,
    syntax_cases=barwarpsync_cases,
    expanded_cases=barwarpsync_expanded,
    negative_cases=barwarpsync_negative,
    empty_target_allowed=lambda coordinates: coordinates["guard"] == "none",
)

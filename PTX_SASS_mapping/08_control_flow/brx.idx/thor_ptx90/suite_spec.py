#!/usr/bin/env python3
"""Independent experiment definition for brx.idx on Thor.

Calibrated against ptxas V13.0.88 / nvdisasm V13.0.85 (`sm_110a`, PTX 9.0):

- `ts: .branchtargets L0, L1, ...; brx.idx %idx, ts;` is the only accepted
  grammar; a bare label or an undeclared symbol as the second operand is
  rejected with "Arguments mismatch for instruction 'brx.idx'". Index must be
  `.b32` (`.b64`/`.f32` rejected with the same diagnostic text).
- O0 always lowers to `BRX Rd -off (*"BRANCH_TARGETS ..."*)` on a GPR. O1-O3
  switch to `BRXU URd (*"BRANCH_TARGETS ..."*)` on a UR *iff* ptxas's
  uniform-value analysis can prove the index is warp-uniform. A `%tid`/
  `%laneid`-derived index stays `BRX` (GPR) at every optimization level.
  Uniformity propagation is itself instruction-selective: `and.b32` on a
  uniform value stays uniform (BRXU), but `rem.u32` on the same uniform
  value is NOT tracked as uniform by this ptxas build and falls back to
  `BRX` -- this suite standardizes on `and.b32` masking for the
  register_uniform axis for that reason (see 实验设计.md "意外发现").
- A compile-time-constant, in-range index folds away completely by O1
  (no BRX at all, straight-line code for the selected arm only); a
  compile-time-constant out-of-range index is accepted with **no static
  diagnostic** at O0 (real BRX, runtime behavior unchecked/undefined) and is
  optimized to a bare EXIT at O3 under an implicit UB assumption. A
  `.branchtargets` list whose destination is degenerate regardless of index
  value (duplicate label, or a single-entry list) also folds away completely
  by O3 even when the index itself is a genuine runtime value.
- `@%p brx.idx %idx, ts;` is legal syntax. It never lowers to a predicated
  BRX form; ptxas always restructures it into an unconditional skip-branch
  around an unconditional BRX. When the guard predicate is warp-uniform, no
  reconvergence bookkeeping appears. When the guard predicate is genuinely
  divergent (tid-derived), the guarded region is wrapped in
  `BSSY.RECONVERGENT` / `BSYNC.RECONVERGENT` -- the same reconvergence-stack
  mechanism used by divergent `bra`/`call` in this family (see
  ../../实验设计.md).
"""

from suite_runtime import Case, Spec

PARAMS_WITH_IDX = (".param .u64 p_out", ".param .u32 p_idx")
PARAMS_NO_IDX = (".param .u64 p_out",)
DIRECTIVES = (".reqntid 128",)

TARGET_LABELS = {
    1: ("L0",),
    2: ("L0", "L1"),
    3: ("L0", "L1", "L2"),
    4: ("L0", "L1", "L2", "L3"),
}


def _mask_for(target_count: int) -> int:
    mask = 1
    while mask < target_count - 1:
        mask = mask * 2 + 1
    return mask


def _index_setup(index_source: str, target_count: int) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    """Returns (extra_registers, extra_preparation, needs_idx_param)."""
    mask = _mask_for(target_count)
    if index_source == "immediate":
        return (), ("mov.u32 %idx, 0;",), False
    if index_source == "register_uniform":
        return (
            (".reg .b32 %raw;",),
            ("ld.param.u32 %raw, [p_idx];", f"and.b32 %idx, %raw, {mask};"),
            True,
        )
    if index_source == "laneid":
        return (
            (".reg .b32 %raw;",),
            ("mov.u32 %raw, %laneid;", f"and.b32 %idx, %raw, {mask};"),
            False,
        )
    raise ValueError(index_source)


def _target_blocks(labels: tuple[str, ...], merge: str) -> tuple[str, ...]:
    lines: list[str] = []
    for index, label in enumerate(labels):
        imm = 111 * (index + 1)
        offset = 4 * index
        lines.append(f"{label}:")
        lines.append(f"    mov.u32 %r0, {imm};")
        lines.append(f"    st.global.b32 [%out+{offset}], %r0;")
        is_last = index == len(labels) - 1
        if merge == "shared":
            if not is_last:
                lines.append("    bra.uni DONE;")
        else:
            lines.append("    ret;")
    if merge == "shared":
        lines.append("DONE:")
        lines.append(f"    mov.u32 %r0, 999;")
        lines.append(f"    st.global.b32 [%out+{4 * len(labels)}], %r0;")
    return tuple(lines)


def _brx_case(
    target_count: int,
    index_source: str,
    merge: str,
    *,
    guard: str = "none",
    context: str = "baseline",
    labels: tuple[str, ...] | None = None,
    parameters: tuple[str, ...] | None = None,
    directives: tuple[str, ...] = DIRECTIVES,
    extra_registers: tuple[str, ...] = (),
    extra_preparation: tuple[str, ...] = (),
) -> Case:
    labels = labels if labels is not None else TARGET_LABELS[target_count]
    extra_regs, extra_prep, needs_idx_param = _index_setup(index_source, target_count)
    coords = {
        "target_count": target_count,
        "index_source": index_source,
        "merge": merge,
        "guard": guard,
        "context": context,
    }
    guard_prefix = ""
    guard_regs: tuple[str, ...] = ()
    guard_prep: tuple[str, ...] = ()
    if guard == "uniform":
        guard_regs = (".reg .pred %p;",)
        guard_prep = ("setp.ne.u32 %p, %raw, 0xFFFFFFFF;",)
        guard_prefix = "@%p "
    elif guard == "divergent":
        guard_regs = (".reg .pred %p;", ".reg .b32 %tg;")
        guard_prep = ("mov.u32 %tg, %tid.x;", "setp.lt.u32 %p, %tg, 16;")
        guard_prefix = "@%p "

    registers = (".reg .b32 %r0, %idx;", *extra_regs, *guard_regs, *extra_registers, ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", *extra_prep, *guard_prep, *extra_preparation)
    target = (f"ts: .branchtargets {', '.join(labels)};", f"{guard_prefix}brx.idx %idx, ts;")
    observation = _target_blocks(labels, merge)
    resolved_params = parameters if parameters is not None else (PARAMS_WITH_IDX if needs_idx_param else PARAMS_NO_IDX)
    return Case(
        "",
        coords,
        parameters=resolved_params,
        registers=registers,
        preparation=preparation,
        target=target,
        observation=observation,
        directives=directives,
    )


def brx_idx_cases() -> list[Case]:
    cases = []
    for target_count in (2, 3, 4):
        for index_source in ("immediate", "register_uniform", "laneid"):
            for merge in ("shared", "separate"):
                cases.append(_brx_case(target_count, index_source, merge))
    return cases


def brx_idx_expanded() -> list[Case]:
    cases = brx_idx_cases()

    # CTX.guard_uniform: warp-uniform guard predicate -- no reconvergence bookkeeping expected.
    cases.append(_brx_case(2, "register_uniform", "shared", guard="uniform", context="guard_uniform"))
    # CTX.guard_divergent: tid-derived guard predicate -- BSSY/BSYNC.RECONVERGENT expected
    # around the guarded region (this family's P0-1 counterpart, see 实验设计.md).
    cases.append(_brx_case(2, "laneid", "shared", guard="divergent", context="guard_divergent"))

    # CTX.index_indirect: index loaded from global memory, not foldable (P1-2).
    indirect_case = _brx_case(
        2,
        "register_uniform",
        "shared",
        context="index_indirect",
        parameters=(".param .u64 p_out", ".param .u64 p_idxptr"),
    )
    indirect_registers = (".reg .b32 %r0, %idx, %raw;", ".reg .b64 %out, %idxptr;")
    indirect_preparation = (
        "ld.param.b64 %out, [p_out];",
        "ld.param.b64 %idxptr, [p_idxptr];",
        "ld.global.u32 %raw, [%idxptr];",
        "and.b32 %idx, %raw, 1;",
    )
    cases.append(Case("", indirect_case.coordinates, parameters=indirect_case.parameters, registers=indirect_registers, preparation=indirect_preparation, target=indirect_case.target, observation=indirect_case.observation, directives=DIRECTIVES))

    # CTX.template_wide: padded/reordered kernel signature (P1-1).
    wide_params = (".param .u32 p_pad0", ".param .u64 p_out", ".param .u64 p_pad1", ".param .u32 p_idx", ".param .u32 p_pad2")
    cases.append(_brx_case(3, "register_uniform", "shared", context="template_wide", parameters=wide_params))

    # CTX.duplicate_target: .branchtargets *lists* the same label twice, but only
    # one physical block named L0 is defined (repeating the label definition
    # itself would be a genuine "Duplicate definition" error, a different and
    # uninteresting failure -- calibration confirmed a repeated *list entry*
    # referencing one real block is legal, a discovery; see 实验设计.md).
    # Destination is degenerate regardless of index, so this folds away
    # entirely by O1-O3: empty_target_allowed handles that.
    dup_registers = (".reg .b32 %r0, %idx, %raw;", ".reg .b64 %out;")
    dup_preparation = ("ld.param.b64 %out, [p_out];", "ld.param.u32 %raw, [p_idx];", "and.b32 %idx, %raw, 1;")
    dup_target = ("ts: .branchtargets L0, L0;", "brx.idx %idx, ts;")
    dup_observation = ("L0:", "    mov.u32 %r0, 111;", "    st.global.b32 [%out], %r0;")
    cases.append(Case("", {"target_count": 2, "index_source": "register_uniform", "merge": "shared", "guard": "none", "context": "duplicate_target"}, parameters=PARAMS_WITH_IDX, registers=dup_registers, preparation=dup_preparation, target=dup_target, observation=dup_observation, directives=DIRECTIVES))

    # CTX.single_target: one-entry .branchtargets (calibrated legal boundary).
    # Also degenerate -> folds away by O1-O3.
    cases.append(_brx_case(1, "register_uniform", "separate", context="single_target"))

    # CTX.double_chain: two independent brx.idx / .branchtargets pairs in one kernel
    # (sequence-level combination, this family's P0-3 counterpart).
    coords = {"target_count": 2, "index_source": "register_uniform", "merge": "shared", "guard": "none", "context": "double_chain"}
    registers = (".reg .b32 %r0, %idx, %idx2, %raw;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", "ld.param.u32 %raw, [p_idx];", "and.b32 %idx, %raw, 1;")
    target = ("ts1: .branchtargets A0, A1;", "brx.idx %idx, ts1;")
    observation = (
        "A0:",
        "    mov.u32 %r0, 10;",
        "    st.global.b32 [%out], %r0;",
        "    bra.uni MID;",
        "A1:",
        "    mov.u32 %r0, 20;",
        "    st.global.b32 [%out+4], %r0;",
        "MID:",
        "    and.b32 %idx2, %raw, 1;",
        "    ts2: .branchtargets B0, B1;",
        "    brx.idx %idx2, ts2;",
        "B0:",
        "    mov.u32 %r0, 30;",
        "    st.global.b32 [%out+8], %r0;",
        "    bra.uni DONE;",
        "B1:",
        "    mov.u32 %r0, 40;",
        "    st.global.b32 [%out+12], %r0;",
        "DONE:",
        "    mov.u32 %r0, 999;",
        "    st.global.b32 [%out+16], %r0;",
    )
    cases.append(Case("", coords, parameters=PARAMS_WITH_IDX, registers=registers, preparation=preparation, target=target, observation=observation, directives=DIRECTIVES))

    return cases


OTHER_FUNC_DECL = (
    ".func other_func()",
    "{",
    "OTHERL2:",
    "    ret;",
    "}",
)


def brx_idx_negative() -> list[Case]:
    def probe(
        probe_name: str,
        target: str,
        reason: str,
        diagnostic: str,
        declarations: tuple[str, ...] = (),
        extra_registers: tuple[str, ...] = (),
    ) -> Case:
        base = _brx_case(2, "register_uniform", "shared", context=probe_name)
        return Case(
            "",
            {"probe": probe_name},
            declarations=declarations,
            parameters=base.parameters,
            registers=base.registers + extra_registers,
            preparation=base.preparation,
            target=(target,),
            observation=(),
            directives=DIRECTIVES,
            expected="reject",
            reason=reason,
            expected_diagnostic=diagnostic,
        )

    return [
        probe(
            "undefined_label",
            "ts: .branchtargets L0, LNOPE;\nbrx.idx %idx, ts;\nL0:\nmov.u32 %r0, 1;\nst.global.b32 [%out], %r0;",
            "branchtargets must reference labels defined in the same function",
            "Unknown symbol 'LNOPE'",
        ),
        probe(
            "cross_function_label",
            "ts: .branchtargets L0, OTHERL2;\nbrx.idx %idx, ts;\nL0:\nmov.u32 %r0, 1;\nst.global.b32 [%out], %r0;",
            "branchtargets cannot reference a label defined inside a different .func, even though that label genuinely exists in the module",
            "Unknown symbol 'OTHERL2'",
            declarations=OTHER_FUNC_DECL,
        ),
        probe(
            "index_type_b64",
            "ts: .branchtargets L0, L1;\nbrx.idx %out, ts;\nL0:\nmov.u32 %r0, 1;\nst.global.b32 [%out], %r0;\nL1:\nmov.u32 %r0, 2;\nst.global.b32 [%out], %r0;",
            "brx.idx index operand must be .b32, not .b64",
            "Arguments mismatch for instruction 'brx.idx'",
        ),
        probe(
            "bare_label_operand",
            "brx.idx %idx, L0;\nL0:\nmov.u32 %r0, 1;\nst.global.b32 [%out], %r0;",
            "second operand must reference a declared .branchtargets symbol, not a bare label",
            "Arguments mismatch for instruction 'brx.idx'",
        ),
        probe(
            "undeclared_symbol_operand",
            "brx.idx %idx, ts_never_declared;\nL0:\nmov.u32 %r0, 1;\nst.global.b32 [%out], %r0;",
            "second operand references a symbol with no .branchtargets declaration anywhere",
            "Unknown symbol 'ts_never_declared'",
        ),
        # complement sampling outside the assumed-legal surface (P0-2)
        probe(
            "index_type_f32",
            "ts: .branchtargets L0, L1;\nbrx.idx %idxf, ts;\nL0:\nmov.u32 %r0, 1;\nst.global.b32 [%out], %r0;\nL1:\nmov.u32 %r0, 2;\nst.global.b32 [%out], %r0;",
            "brx.idx index operand must be an integer register, not .f32 (complement sample)",
            "Arguments mismatch for instruction 'brx.idx'",
            extra_registers=(".reg .f32 %idxf;",),
        ),
        probe(
            "empty_branchtargets",
            "ts: .branchtargets;\nbrx.idx %idx, ts;",
            "an empty .branchtargets list has no valid destination (complement sample)",
            "Parsing error near ';': syntax error",
        ),
    ]


FACTORS = (
    {"id": "SF.target_count", "levels": [1, 2, 3, 4]},
    {"id": "SF.index_source", "levels": ["immediate", "register_uniform", "laneid"]},
    {"id": "SF.merge", "levels": ["shared", "separate"]},
    {"id": "SF.guard", "levels": ["none", "uniform", "divergent"]},
    {"id": "CTX.context", "levels": ["baseline", "guard_uniform", "guard_divergent", "index_indirect", "template_wide", "duplicate_target", "single_target", "double_chain"]},
)


def _empty_target_allowed(coordinates: dict) -> bool:
    if coordinates.get("index_source") == "immediate":
        return True
    if coordinates.get("context") in ("duplicate_target", "single_target"):
        return True
    return False


SPEC = Spec(
    family="cf",
    opcode="brx_idx",
    ptx_opcode="brx.idx",
    target_patterns=("BRX",),
    factors=FACTORS,
    syntax_cases=brx_idx_cases,
    expanded_cases=brx_idx_expanded,
    negative_cases=brx_idx_negative,
    empty_target_allowed=_empty_target_allowed,
)

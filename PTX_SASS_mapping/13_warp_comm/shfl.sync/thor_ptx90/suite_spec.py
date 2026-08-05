#!/usr/bin/env python3
"""Independent experiment definition for shfl.sync on Thor.

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 (`sm_110a`, PTX 9.0): shfl.sync.{up,down,bfly,idx}.b32
lowers to SHFL.{UP,DOWN,BFLY,IDX} {Pd|PT}, Rd, Ra, {b_imm|Rb}, {c_imm|Rc}.
The `d|p` predicate slot maps to a real predicate register when requested,
PT (always-true, unused) otherwise. `b` and `c` are PTX-level operands that
accept either an immediate literal or a register directly (no separate
"literal" grammar); a register holding a compile-time-provable constant
still folds into the SASS immediate field, so the register-operand axis
below always sources its value from a per-lane-varying special register
(`%tid.y`/`%tid.z`) to force a genuine SASS register operand.

The membermask never appears as a SHFL operand. Instead it controls whether
a WARPSYNC precedes the SHFL and in what form:

  - at a point already known to be warp-convergent (function entry, no
    prior divergent branch), WARPSYNC is elided for a full-warp immediate
    mask (0xffffffff) AND for any other immediate or provably-uniform
    runtime mask (kernel-param load, ballot-of-uniform-predicate result,
    constant-propagated register) -- ptxas does not statically verify that
    the declared mask matches the actual active set;
  - a runtime register mask that is not provably uniform (derived from
    %tid.x) gets an explicit `WARPSYNC Rn` (plain GPR operand) before the
    SHFL, even at a convergent point;
  - once real control-flow divergence has occurred, a full immediate mask
    needs an explicit `WARPSYNC.ALL` (no operand); a partial-immediate or
    uniform-but-not-full mask needs an explicit `WARPSYNC Rn`.

WARPSYNC was never observed to take a UR (uniform register) operand in any
tested configuration -- membermask uniformity gates *whether* WARPSYNC is
emitted, not its register class. See `../实验设计.md` for the full
calibration record and falsified hypotheses (P0-2).

A second falsified-then-confirmed mechanism: if the `a` operand is
compiler-provably warp-uniform (e.g. loaded straight from a `.param`),
shuffling it is an algebraic no-op and ptxas eliminates the SHFL entirely
(zero occurrences in the disassembly). The `uniform_source_elimination`
context case below exercises this and is the sole `empty_target_allowed`
coordinate in this suite.
"""

from suite_runtime import Case, Spec

MODES = ("up", "down", "bfly", "idx")

FULL_MASK = "0xffffffff"
PARTIAL_MASK = "0x0000ffff"
ZERO_MASK = "0x00000000"

PARAMS = (".param .u64 p_out",)
PARAMS_WITH_MASK_PARAM = (".param .u64 p_out", ".param .u32 p_mask")


def _reg_block() -> tuple[str, ...]:
    return (
        ".reg .b32 %t0, %rb, %rc, %m, %r3, %r4;",
        ".reg .pred %p0;",
        ".reg .b64 %out;",
    )


def _prep_block(b_form: str, c_form: str, mask_form: str) -> tuple[str, ...]:
    prep = ["ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;"]
    if b_form == "reg":
        prep.append("mov.u32 %rb, %tid.y;")
    if c_form == "reg":
        prep.append("mov.u32 %rc, %tid.z;")
    if mask_form == "reg_nonuniform":
        prep.append("mov.u32 %m, %tid.x;")
    elif mask_form == "reg_uniform_param":
        prep.append("ld.param.u32 %m, [p_mask];")
    return tuple(prep)


def _params(mask_form: str) -> tuple[str, ...]:
    return PARAMS_WITH_MASK_PARAM if mask_form == "reg_uniform_param" else PARAMS


def _mask_operand(mask_form: str) -> str:
    return {
        "full_imm": FULL_MASK,
        "partial_imm": PARTIAL_MASK,
        "zero_imm": ZERO_MASK,
        "reg_nonuniform": "%m",
        "reg_uniform_param": "%m",
    }[mask_form]


def _shfl_text(mode: str, pred: bool, b_form: str, c_form: str, mask_form: str, guard: str = "", a_reg: str = "%t0", d_reg: str = "%r3") -> str:
    dest = f"{d_reg}|%p0" if pred else d_reg
    b = "1" if b_form == "imm" else "%rb"
    c = "0x1f" if c_form == "imm" else "%rc"
    mask = _mask_operand(mask_form)
    return f"{guard}shfl.sync.{mode}.b32 {dest}, {a_reg}, {b}, {c}, {mask};"


def _observation(pred: bool) -> tuple[str, ...]:
    if pred:
        return ("selp.b32 %r4, 1, 0, %p0;", "add.u32 %r3, %r3, %r4;", "st.global.b32 [%out], %r3;")
    return ("st.global.b32 [%out], %r3;",)


def _case(mode: str, pred: bool, b_form: str, c_form: str, mask_form: str, context: str = "baseline") -> Case:
    coords = {"mode": mode, "pred": pred, "b_form": b_form, "c_form": c_form, "mask_form": mask_form, "context": context}
    return Case(
        "",
        coords,
        parameters=_params(mask_form),
        registers=_reg_block(),
        preparation=_prep_block(b_form, c_form, mask_form),
        target=(_shfl_text(mode, pred, b_form, c_form, mask_form),),
        observation=_observation(pred),
    )


def shfl_syntax_cases() -> list[Case]:
    cases = []
    # 1. baseline: mode x predicate destination, full mask, immediate b/c (8)
    for mode in MODES:
        for pred in (False, True):
            cases.append(_case(mode, pred, "imm", "imm", "full_imm"))
    # 2. b operand as a genuine register, all four modes (4)
    for mode in MODES:
        cases.append(_case(mode, False, "reg", "imm", "full_imm"))
    # 3. c operand as a genuine register, all four modes (4)
    for mode in MODES:
        cases.append(_case(mode, False, "imm", "reg", "full_imm"))
    # 4. both b and c as registers (dual operand-form combination) (2)
    for mode in ("bfly", "idx"):
        cases.append(_case(mode, False, "reg", "reg", "full_imm"))
    # 5. dual-modifier: predicate destination x register b (2)
    for mode in ("up", "down"):
        cases.append(_case(mode, True, "reg", "imm", "full_imm"))
    # 6. dual-modifier: predicate destination x register c (2)
    for mode in ("bfly", "idx"):
        cases.append(_case(mode, True, "imm", "reg", "full_imm"))
    # 7. membermask axis: non-full immediate mask, all four modes (4)
    for mode in MODES:
        cases.append(_case(mode, False, "imm", "imm", "partial_imm"))
    # 8. membermask axis: register, not provably uniform (tid-derived), all four modes (4)
    for mode in MODES:
        cases.append(_case(mode, False, "imm", "imm", "reg_nonuniform"))
    # 9. membermask axis: register, provably uniform (loaded from .param) (2)
    for mode in ("up", "idx"):
        cases.append(_case(mode, False, "imm", "imm", "reg_uniform_param"))
    # 10. dual-modifier: predicate destination x non-full immediate mask (2)
    for mode in ("bfly", "idx"):
        cases.append(_case(mode, True, "imm", "imm", "partial_imm"))
    return cases


def _indirect_case(mode: str) -> Case:
    """P1-2: `a` sourced from a tid-indexed global load (non-foldable, non-uniform)."""
    coords = {"mode": mode, "pred": False, "b_form": "imm", "c_form": "imm", "mask_form": "full_imm", "context": "lane_source_indirect_producer"}
    registers = (".reg .b32 %t0, %r3, %a;", ".reg .b64 %out, %in, %addr;")
    preparation = (
        "ld.param.b64 %out, [p_out];",
        "ld.param.b64 %in, [p_in];",
        "mov.u32 %t0, %tid.x;",
        "mul.wide.u32 %addr, %t0, 4;",
        "add.s64 %addr, %addr, %in;",
        "ld.global.b32 %a, [%addr];",
    )
    target = (f"shfl.sync.{mode}.b32 %r3, %a, 1, 0x1f, {FULL_MASK};",)
    observation = ("st.global.b32 [%out], %r3;",)
    return Case("", coords, parameters=(".param .u64 p_out", ".param .u64 p_in"), registers=registers, preparation=preparation, target=target, observation=observation)


def _chained_case(mode1: str, mode2: str) -> Case:
    """A collective result feeding a second collective as its lane source."""
    coords = {"mode": f"{mode1}+{mode2}", "pred": False, "b_form": "imm", "c_form": "imm", "mask_form": "full_imm", "context": "chained_shfl"}
    registers = (".reg .b32 %t0, %r3, %r4;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;")
    target = (
        f"shfl.sync.{mode1}.b32 %r3, %t0, 1, 0x1f, {FULL_MASK};",
        f"shfl.sync.{mode2}.b32 %r4, %r3, 1, 0x1f, {FULL_MASK};",
    )
    observation = ("st.global.b32 [%out], %r4;",)
    return Case("", coords, parameters=PARAMS, registers=registers, preparation=preparation, target=target, observation=observation)


def _uniform_elimination_case() -> Case:
    """Falsifies "shfl always lowers to SHFL": a provably-uniform source
    makes the shuffle an algebraic no-op and ptxas drops it entirely."""
    coords = {"mode": "up", "pred": False, "b_form": "imm", "c_form": "imm", "mask_form": "full_imm", "context": "uniform_source_elimination"}
    registers = (".reg .b32 %v, %r3;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", "ld.param.u32 %v, [p_val];")
    target = (f"shfl.sync.up.b32 %r3, %v, 1, 0x1f, {FULL_MASK};",)
    observation = ("st.global.b32 [%out], %r3;",)
    return Case("", coords, parameters=(".param .u64 p_out", ".param .u32 p_val"), registers=registers, preparation=preparation, target=target, observation=observation)


def _guard_case(mode: str) -> Case:
    """P0-1 analog: predicated issue forces real control flow, and a full
    mask past a divergence point needs an explicit WARPSYNC.ALL."""
    coords = {"mode": mode, "pred": False, "b_form": "imm", "c_form": "imm", "mask_form": "full_imm", "context": "guard_full_mask"}
    registers = (".reg .b32 %t0, %r3;", ".reg .pred %pg;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;", "mov.u32 %r3, %t0;", "setp.lt.u32 %pg, %t0, 100000;")
    target = (f"@%pg shfl.sync.{mode}.b32 %r3, %t0, 1, 0x1f, {FULL_MASK};",)
    observation = ("st.global.b32 [%out], %r3;",)
    return Case("", coords, parameters=PARAMS, registers=registers, preparation=preparation, target=target, observation=observation)


def _divergent_reg_mask_case() -> Case:
    """Non-uniform register mask inside real divergence -> WARPSYNC(.EXCLUSIVE) Rn."""
    coords = {"mode": "up", "pred": False, "b_form": "imm", "c_form": "imm", "mask_form": "reg_nonuniform", "context": "divergent_reg_mask"}
    registers = (".reg .b32 %t0, %r3, %m;", ".reg .pred %pu;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;", "mov.u32 %m, %t0;", "setp.lt.u32 %pu, %t0, 16;", "@!%pu bra SHFL_SKIP_RM;")
    target = ("shfl.sync.up.b32 %r3, %t0, 1, 0x1f, %m;",)
    observation = ("bra SHFL_STORE_RM;", "SHFL_SKIP_RM:", "mov.u32 %r3, %t0;", "SHFL_STORE_RM:", "st.global.b32 [%out], %r3;")
    return Case("", coords, parameters=PARAMS, registers=registers, preparation=preparation, target=target, observation=observation)


def _divergent_matched_partial_mask_case() -> Case:
    """Contrast case: the non-full immediate mask exactly matches the branch
    condition that reaches it (lanes 0-15, mask 0x0000ffff) -- a correctly
    scoped collective, as opposed to the convergent-point partial-mask case
    where 32 threads reach a 16-lane mask unconditionally."""
    coords = {"mode": "up", "pred": False, "b_form": "imm", "c_form": "imm", "mask_form": "partial_imm", "context": "divergent_matched_partial_mask"}
    registers = (".reg .b32 %t0, %r3;", ".reg .pred %pu;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;", "setp.lt.u32 %pu, %t0, 16;", "@!%pu bra SHFL_SKIP_PM;")
    target = (f"shfl.sync.up.b32 %r3, %t0, 1, 0x1f, {PARTIAL_MASK};",)
    observation = ("bra SHFL_STORE_PM;", "SHFL_SKIP_PM:", "mov.u32 %r3, %t0;", "SHFL_STORE_PM:", "st.global.b32 [%out], %r3;")
    return Case("", coords, parameters=PARAMS, registers=registers, preparation=preparation, target=target, observation=observation)


def _mask_zero_case() -> Case:
    """STATIC_ONLY boundary, recorded separately: mask=0 declares zero
    participants while all 32 lanes reach this point unconditionally.
    ptxas accepts it (no static verification of the collective
    precondition) -- see 实验设计.md's collective precondition ledger."""
    coords = {"mode": "up", "pred": False, "b_form": "imm", "c_form": "imm", "mask_form": "zero_imm", "context": "collective_precondition_violation_zero_mask"}
    registers = (".reg .b32 %t0, %r3;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;")
    target = (f"shfl.sync.up.b32 %r3, %t0, 1, 0x1f, {ZERO_MASK};",)
    observation = ("st.global.b32 [%out], %r3;",)
    return Case("", coords, parameters=PARAMS, registers=registers, preparation=preparation, target=target, observation=observation)


def _template_wide_case() -> Case:
    """P1-1: padded/reordered kernel parameter signature."""
    coords = {"mode": "up", "pred": False, "b_form": "imm", "c_form": "imm", "mask_form": "full_imm", "context": "template_wide"}
    wide_params = (".param .u32 p_pad0", ".param .u64 p_out", ".param .u64 p_pad1", ".param .u32 p_pad2")
    registers = (".reg .b32 %t0, %r3;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;")
    target = (f"shfl.sync.up.b32 %r3, %t0, 1, 0x1f, {FULL_MASK};",)
    observation = ("st.global.b32 [%out], %r3;",)
    return Case("", coords, parameters=wide_params, registers=registers, preparation=preparation, target=target, observation=observation)


def _consume_distance_case() -> Case:
    """Control-resource axis: several filler instructions between the
    collective and its consumer."""
    coords = {"mode": "up", "pred": False, "b_form": "imm", "c_form": "imm", "mask_form": "full_imm", "context": "consume_distance_8"}
    registers = (".reg .b32 %t0, %r3, %f;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;", "mov.u32 %f, 0;")
    target = (f"shfl.sync.up.b32 %r3, %t0, 1, 0x1f, {FULL_MASK};",)
    filler = tuple("add.u32 %f, %f, 1;" for _ in range(8))
    observation = (*filler, "add.u32 %r3, %r3, %f;", "st.global.b32 [%out], %r3;")
    return Case("", coords, parameters=PARAMS, registers=registers, preparation=preparation, target=target, observation=observation)


def shfl_expanded_cases() -> list[Case]:
    cases = shfl_syntax_cases()
    cases.append(_indirect_case("up"))
    cases.append(_indirect_case("bfly"))
    cases.append(_chained_case("up", "bfly"))
    cases.append(_chained_case("down", "idx"))
    cases.append(_uniform_elimination_case())
    cases.append(_guard_case("up"))
    cases.append(_guard_case("idx"))
    cases.append(_divergent_reg_mask_case())
    cases.append(_divergent_matched_partial_mask_case())
    cases.append(_mask_zero_case())
    cases.append(_template_wide_case())
    cases.append(_consume_distance_case())
    return cases


def _negative(coords: dict, registers: tuple[str, ...], preparation: tuple[str, ...], target: str, reason: str, diagnostic: str, parameters: tuple[str, ...] = PARAMS) -> Case:
    return Case("", coords, parameters=parameters, registers=registers, preparation=preparation, target=(target,), observation=(), expected="reject", reason=reason, expected_diagnostic=diagnostic)


def shfl_negative_cases() -> list[Case]:
    base_regs = _reg_block()
    base_prep = _prep_block("imm", "imm", "full_imm")
    return [
        # diagnostic-anchored (guide-mandated): missing .sync
        _negative(
            {"probe": "legacy_no_sync"}, base_regs, base_prep,
            "shfl.up.b32 %r3, %t0, 1, 0x1f;",
            "legacy 3-operand shfl without .sync is illegal on sm_70+ since PTX ISA 6.4",
            "Instruction 'shfl' without '.sync' is not supported on .target sm_70 and higher from PTX ISA version 6.4",
        ),
        # diagnostic-anchored: b64 data width
        _negative(
            {"probe": "b64_data_width"},
            (".reg .b64 %t0d, %r3d;", ".reg .b64 %out;"),
            ("ld.param.b64 %out, [p_out];", "cvt.u64.u32 %t0d, %tid.x;"),
            "shfl.sync.up.b64 %r3d, %t0d, 1, 0x1f, 0xffffffff;",
            "shfl operates on .b32 only; .b64 data width is illegal",
            "Unexpected instruction types specified for 'shfl'",
        ),
        # diagnostic-anchored: mask type error (f32 register in the mask slot)
        _negative(
            {"probe": "mask_type_f32"},
            (".reg .b32 %t0, %r3;", ".reg .f32 %mf;", ".reg .b64 %out;"),
            ("ld.param.b64 %out, [p_out];", "mov.u32 %t0, %tid.x;", "mov.f32 %mf, 0f00000000;"),
            "shfl.sync.up.b32 %r3, %t0, 1, 0x1f, %mf;",
            "membermask must be a .b32/.u32-typed value, not .f32",
            "Arguments mismatch for instruction 'shfl'",
        ),
        # complement sample 1: .u32 is not a defined shfl type (only .b32 is)
        _negative(
            {"probe": "complement_u32_type_token"}, base_regs, base_prep,
            "shfl.sync.up.u32 %r3, %t0, 1, 0x1f, 0xffffffff;",
            "complement sampling: .u32 type token outside the calibrated .b32-only surface",
            "Unexpected instruction types specified for 'shfl'",
        ),
        # complement sample 2: truncated 4-operand .sync form (missing c)
        _negative(
            {"probe": "complement_missing_c_operand"}, base_regs, base_prep,
            "shfl.sync.up.b32 %r3, %t0, 1, 0xffffffff;",
            "complement sampling: .sync form requires a, b, c, membermask (4 operands); omitting c is untested by the calibrated matrix",
            "Arguments mismatch for instruction 'shfl'",
        ),
        # complement sample 3: non-predicate register in the |p destination slot
        _negative(
            {"probe": "complement_pred_slot_type"}, base_regs, base_prep,
            "shfl.sync.up.b32 %r3|%r4, %t0, 1, 0x1f, 0xffffffff;",
            "complement sampling: the |p slot requires a .pred register, not a .b32 register",
            "Predicate output expected for instruction 'shfl'",
        ),
    ]


FACTORS = (
    {"id": "SF.mode", "levels": ["up", "down", "bfly", "idx"]},
    {"id": "SF.pred", "levels": [False, True]},
    {"id": "SF.b_form", "levels": ["imm", "reg"]},
    {"id": "SF.c_form", "levels": ["imm", "reg"]},
    {"id": "SF.mask_form", "levels": ["full_imm", "partial_imm", "zero_imm", "reg_nonuniform", "reg_uniform_param"]},
    {"id": "CTX.context", "levels": [
        "baseline", "lane_source_indirect_producer", "chained_shfl", "uniform_source_elimination",
        "guard_full_mask", "divergent_reg_mask", "divergent_matched_partial_mask",
        "collective_precondition_violation_zero_mask", "template_wide", "consume_distance_8",
    ]},
)

SPEC = Spec(
    family="warp",
    opcode="shfl_sync",
    ptx_opcode="shfl.sync",
    target_patterns=("SHFL",),
    factors=FACTORS,
    syntax_cases=shfl_syntax_cases,
    expanded_cases=shfl_expanded_cases,
    negative_cases=shfl_negative_cases,
    empty_target_allowed=lambda coordinates: coordinates.get("context") == "uniform_source_elimination",
)

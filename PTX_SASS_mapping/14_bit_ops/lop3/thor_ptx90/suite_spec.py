#!/usr/bin/env python3
"""Independent experiment definition for lop3 on Thor.

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 (`sm_110a`, PTX 9.0) with disposable scratchpad probes
(not checked in; reproducible via the case bodies below). Calibration
findings that shape this spec:

1. `lop3.b32 d, a, b, c, immLut;` lowers to a single `LOP3.LUT` with a
   trailing `!PT` operand (a predicate slot that stays `!PT` unless the
   BoolOp/predicate form is used). immLut passes through to the SASS
   immediate literally ONLY when the PTX operand supplying the immediate
   already lands in PTX's second (`b`) source position -- hardware fixes
   exactly one immediate slot at that physical position. If the immediate
   is written in PTX's `a` or `c` position instead, ptxas swaps the two
   register operands into the hardware's other two slots and ALGEBRAICALLY
   PERMUTES immLut so the 3-input truth table still matches: with the
   asymmetric probe LUT 0x30 (`a & ~b`, ignoring c), `a`-slot immediate
   emits SASS immLut 0xc, `c`-slot immediate emits 0x50, `b`-slot immediate
   is unchanged at 0x30. A literal PTX `0` in any slot is NOT treated as an
   immediate at all -- it is encoded directly as the `RZ` register with no
   reordering and no LUT permutation, which is why "zero" is tracked here
   as a third source-slot class distinct from "register" and "immediate".
2. Two or three simultaneous immediate source operands are syntactically
   legal (not rejected); since hardware has only one immediate slot,
   ptxas materializes the extra literals into registers via `MOV` before
   `LOP3.LUT`, keeping exactly one true literal in the encoding.
3. immLut (and immLut2, see below) are NOT statically range-checked to 8
   bits: `immLut=0x100` compiles and is silently truncated to `0x0`;
   `immLut=-1` compiles and wraps to `0xff`. This is a P0-2 "predicted
   illegal but accepted" discovery, so these live in `lop3_expanded`
   (positive matrix, `context=discovery_*`), not in the negative probes.
4. `lop3.BoolOp.b32 d|p, a, b, c, immLut, immLut2;` is real, accepted PTX
   9.0 syntax on this target with `BoolOp = {.and, .or}` (`.xor` is
   explicitly rejected); both modifier-order spellings (`lop3.and.b32` and
   `lop3.b32.and`) are accepted, mirroring the TMA family's
   `cta_group`-position finding. When both `d` and `p` are actually
   consumed, ptxas lowers the ONE PTX instruction to TWO SASS
   instructions: `LOP3.LUT.PAND Rd, Ra, Rb, Rc, immLut, Pg` (value) and
   `LOP3.LUT.PAND Pd, RZ, Ra, Rb, Rc, immLut, Pg` (predicate) -- a 1-to-2
   lowering. If `p` is left unconsumed, only the register form survives.
   immLut2's own numeric value was never observed inside the SASS
   encoding; the only observed effect across immLut2 in {0x00, 0xff,
   0xc0, 0x3c, 0x0f} is that a zero immLut2 flips the trailing predicate
   literal from `PT` to `!PT`. This is recorded as an open, STATIC_ONLY
   question (not a confirmed semantic rule) -- see `实验设计.md`.
5. `lop3` has no `.b64` form (`Unexpected instruction types`), no
   sub-`.b32` or differently-signed type spelling (`.u32`/`.s32`/`.f32`/
   `.b16` all rejected the same way -- lop3 is `.b32`-only on this
   target), no register-valued immLut/immLut2 (`Arguments mismatch`), and
   no unary `!`/`-` operand-negation modifiers on its sources
   (`Illegal argument to predicate negation` / `Operand negation not
   allowed for instruction 'lop3'`) -- negation is folded into the LUT
   choice itself, not a separate operand modifier.
6. A guard predicate on `lop3.b32` does not survive as `@P LOP3` in the
   O0 disassembly: ptxas computes LOP3 unconditionally and if-converts
   the guard into a trailing `SEL` merge. Repeated sources (`a==b`,
   `a==b==c`) are fully legal and produce a single `LOP3.LUT` with the
   repeated register in multiple slots.
7. At O0 two textually-identical `lop3.b32` instructions are NOT
   CSE'd (two `LOP3.LUT` survive); at O3 they ARE merged into one
   `LOP3.LUT` feeding both stores -- this is the flagship's `dedup_o3`
   case, and the differing per-optimization occurrence count is expected,
   not a suite bug.

Consumers in every case store each computed value directly via
`st.global` (never `xor`/`and`/`or`-combine two results before storing):
per the family's high-risk-cluster warning, lop3's own SASS mnemonic is
what a combining consumer would itself lower to, which would silently
inflate `LOP3` attribution counts with instructions that are not the
case's declared target.
"""

import itertools

from suite_runtime import Case, Spec

PARAMS1 = (".param .u64 p_out",)
PARAMS2 = (".param .u64 p_out0", ".param .u64 p_out1")
PARAMS_INDIRECT = (".param .u64 p_src", ".param .u64 p_out")
PARAMS_WIDE = (".param .u32 p_pad0", ".param .u64 p_out", ".param .u32 p_pad1", ".param .u64 p_pad2")
DIRECTIVES = (".reqntid 128",)

IMMLUT_LEVELS = ("0x00", "0xff", "0xaa", "0x96", "0xe8", "0x1a")
A_IMM, B_IMM, C_IMM = "0x0f0f0f0f", "0x33333333", "0x55555555"


def _base_regs(extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    return (".reg .b32 %t0, %t1, %t2, %r0;", ".reg .b64 %out;", *extra)


def _base_prep(extra_before: tuple[str, ...] = ()) -> tuple[str, ...]:
    return (
        "ld.param.b64 %out, [p_out];",
        "mov.u32 %t0, %tid.x;",
        "mov.u32 %t1, %ctaid.x;",
        "mov.u32 %t2, %ntid.x;",
        *extra_before,
    )


def _simple_case(coords: dict, target_line: str, extra_regs: tuple[str, ...] = (), extra_prep: tuple[str, ...] = ()) -> Case:
    return Case(
        "",
        coords,
        parameters=PARAMS1,
        registers=_base_regs(extra_regs),
        preparation=_base_prep(extra_prep),
        target=(target_line,),
        observation=("st.global.b32 [%out], %r0;",),
        directives=DIRECTIVES,
    )


# --- 1. immLut sweep: all-register operands, immLut in the six calibrated levels ---

def _immlut_sweep() -> list[Case]:
    cases = []
    for lut in IMMLUT_LEVELS:
        coords = {"axis": "immlut_sweep", "a_class": "reg", "b_class": "reg", "c_class": "reg", "immlut": lut, "boolop": "none", "context": "baseline"}
        cases.append(_simple_case(coords, f"lop3.b32 %r0, %t0, %t1, %t2, {lut};"))
    return cases


# --- 2. source-slot operand class: a/b/c independently reg/imm/zero, immLut=0xaa (asymmetric: F=c) ---

def _slot_text(cls: str, reg: str, imm: str) -> str:
    return {"reg": reg, "imm": imm, "zero": "0"}[cls]


def _slot_class_matrix() -> list[Case]:
    cases = []
    for a_cls, b_cls, c_cls in itertools.product(("reg", "imm", "zero"), repeat=3):
        a = _slot_text(a_cls, "%t0", A_IMM)
        b = _slot_text(b_cls, "%t1", B_IMM)
        c = _slot_text(c_cls, "%t2", C_IMM)
        coords = {"axis": "slot_class", "a_class": a_cls, "b_class": b_cls, "c_class": c_cls, "immlut": "0xaa", "boolop": "none", "context": "baseline"}
        cases.append(_simple_case(coords, f"lop3.b32 %r0, {a}, {b}, {c}, 0xaa;"))
    return cases


# --- 3. BoolOp predicate-output form: and/or x two accepted spelling orders ---

def _boolop_case(boolop: str, spelling: str, immlut: str, immlut2: str, context: str) -> Case:
    mnemonic = f"lop3.{boolop}.b32" if spelling == "boolop_first" else f"lop3.b32.{boolop}"
    coords = {"axis": "boolop_form", "a_class": "reg", "b_class": "reg", "c_class": "reg", "immlut": immlut, "immlut2": immlut2, "boolop": boolop, "spelling": spelling, "context": context}
    return Case(
        "",
        coords,
        parameters=PARAMS2,
        registers=(".reg .b32 %t0, %t1, %t2, %r0, %sel;", ".reg .pred %p0;", ".reg .b64 %out0, %out1;"),
        preparation=(
            "ld.param.b64 %out0, [p_out0];",
            "ld.param.b64 %out1, [p_out1];",
            "mov.u32 %t0, %tid.x;",
            "mov.u32 %t1, %ctaid.x;",
            "mov.u32 %t2, %ntid.x;",
        ),
        target=(f"{mnemonic} %r0|%p0, %t0, %t1, %t2, {immlut}, {immlut2};",),
        observation=("selp.b32 %sel, 1, 0, %p0;", "st.global.b32 [%out0], %r0;", "st.global.b32 [%out1], %sel;"),
        directives=DIRECTIVES,
    )


def _boolop_forms() -> list[Case]:
    cases = []
    for boolop in ("and", "or"):
        for spelling in ("boolop_first", "b32_first"):
            cases.append(_boolop_case(boolop, spelling, "0x96", "0xc0", "baseline"))
    return cases


def lop3_syntax_cases() -> list[Case]:
    return _immlut_sweep() + _slot_class_matrix() + _boolop_forms()


# --- expanded: additional context axes on top of the syntax matrix ---

def _repeated_source_cases() -> list[Case]:
    combos = [
        ("ab", "lop3.b32 %r0, %t0, %t0, %t2, 0xaa;"),
        ("ac", "lop3.b32 %r0, %t0, %t1, %t0, 0xaa;"),
        ("bc", "lop3.b32 %r0, %t0, %t1, %t1, 0xaa;"),
        ("abc", "lop3.b32 %r0, %t0, %t0, %t0, 0xaa;"),
    ]
    cases = []
    for tag, line in combos:
        coords = {"axis": "repeated_source", "repeat": tag, "immlut": "0xaa", "boolop": "none", "context": f"repeat_{tag}"}
        cases.append(_simple_case(coords, line))
    return cases


def _indirect_case(which: str) -> Case:
    a = "%m0" if which in ("a", "all") else "%t0"
    b = "%m1" if which in ("b", "all") else "%t1"
    c = "%m2" if which in ("c", "all") else "%t2"
    coords = {"axis": "indirect_producer", "operand": which, "immlut": "0x96", "boolop": "none", "context": f"indirect_{which}"}
    return Case(
        "",
        coords,
        parameters=PARAMS_INDIRECT,
        registers=(".reg .b32 %t0, %t1, %t2, %r0, %m0, %m1, %m2;", ".reg .b64 %src, %out;"),
        preparation=(
            "ld.param.b64 %src, [p_src];",
            "ld.param.b64 %out, [p_out];",
            "mov.u32 %t0, %tid.x;",
            "mov.u32 %t1, %ctaid.x;",
            "mov.u32 %t2, %ntid.x;",
            "ld.global.b32 %m0, [%src];",
            "ld.global.b32 %m1, [%src+4];",
            "ld.global.b32 %m2, [%src+8];",
        ),
        target=(f"lop3.b32 %r0, {a}, {b}, {c}, 0x96;",),
        observation=("st.global.b32 [%out], %r0;",),
        directives=DIRECTIVES,
    )


def _indirect_producer_cases() -> list[Case]:
    return [_indirect_case(which) for which in ("a", "b", "c", "all")]


def _chain_case() -> Case:
    coords = {"axis": "sequence", "context": "double_chain", "immlut": "0x96/0xe8", "boolop": "none"}
    return Case(
        "",
        coords,
        parameters=PARAMS1,
        registers=(".reg .b32 %t0, %t1, %t2, %r0, %r1;", ".reg .b64 %out;"),
        preparation=_base_prep(),
        target=("lop3.b32 %r0, %t0, %t1, %t2, 0x96;", "lop3.b32 %r1, %r0, %t0, %t1, 0xe8;"),
        observation=("st.global.b32 [%out], %r1;",),
        directives=DIRECTIVES,
    )


def _reuse_diff_operands_case() -> Case:
    coords = {"axis": "sequence", "context": "reuse_lut_diff_operands", "immlut": "0x96", "boolop": "none"}
    return Case(
        "",
        coords,
        parameters=PARAMS2,
        registers=(".reg .b32 %t0, %t1, %t2, %r0, %r1;", ".reg .b64 %out0, %out1;"),
        preparation=(
            "ld.param.b64 %out0, [p_out0];",
            "ld.param.b64 %out1, [p_out1];",
            "mov.u32 %t0, %tid.x;",
            "mov.u32 %t1, %ctaid.x;",
            "mov.u32 %t2, %ntid.x;",
        ),
        target=("lop3.b32 %r0, %t0, %t1, %t2, 0x96;", "lop3.b32 %r1, %t1, %t2, %t0, 0x96;"),
        observation=("st.global.b32 [%out0], %r0;", "st.global.b32 [%out1], %r1;"),
        directives=DIRECTIVES,
    )


def _reuse_exact_duplicate_case() -> Case:
    coords = {"axis": "sequence", "context": "dedup_o3", "immlut": "0x96", "boolop": "none"}
    return Case(
        "",
        coords,
        parameters=PARAMS2,
        registers=(".reg .b32 %t0, %t1, %t2, %r0, %r1;", ".reg .b64 %out0, %out1;"),
        preparation=(
            "ld.param.b64 %out0, [p_out0];",
            "ld.param.b64 %out1, [p_out1];",
            "mov.u32 %t0, %tid.x;",
            "mov.u32 %t1, %ctaid.x;",
            "mov.u32 %t2, %ntid.x;",
        ),
        target=("lop3.b32 %r0, %t0, %t1, %t2, 0x96;", "lop3.b32 %r1, %t0, %t1, %t2, 0x96;"),
        observation=("st.global.b32 [%out0], %r0;", "st.global.b32 [%out1], %r1;"),
        directives=DIRECTIVES,
    )


def _guard_case() -> Case:
    coords = {"axis": "context", "context": "guarded", "immlut": "0x96", "boolop": "none"}
    return Case(
        "",
        coords,
        parameters=PARAMS1,
        registers=(".reg .b32 %t0, %t1, %t2, %r0;", ".reg .pred %p0;", ".reg .b64 %out;"),
        preparation=(*_base_prep(), "setp.lt.u32 %p0, %t0, 16;"),
        target=("@%p0 lop3.b32 %r0, %t0, %t1, %t2, 0x96;",),
        observation=("st.global.b32 [%out], %r0;",),
        directives=DIRECTIVES,
    )


def _template_wide_case() -> Case:
    coords = {"axis": "context", "context": "template_wide", "immlut": "0x96", "boolop": "none"}
    return Case(
        "",
        coords,
        parameters=PARAMS_WIDE,
        registers=_base_regs(),
        preparation=_base_prep(),
        target=("lop3.b32 %r0, %t0, %t1, %t2, 0x96;",),
        observation=("st.global.b32 [%out], %r0;",),
        directives=DIRECTIVES,
    )


def _boolop_immlut2_sweep() -> list[Case]:
    return [_boolop_case("and", "boolop_first", "0x96", lut2, f"immlut2_{lut2}") for lut2 in ("0x00", "0xff", "0x3c", "0x0f")]


def _discovery_cases() -> list[Case]:
    cases = []
    coords = {"axis": "discovery", "context": "immlut_9bit_truncation", "immlut": "0x100", "boolop": "none"}
    cases.append(_simple_case(coords, "lop3.b32 %r0, %t0, %t1, %t2, 0x100;"))
    coords = {"axis": "discovery", "context": "immlut_negative_wraparound", "immlut": "-1", "boolop": "none"}
    cases.append(_simple_case(coords, "lop3.b32 %r0, %t0, %t1, %t2, -1;"))
    coords = {"axis": "discovery", "context": "immlut2_9bit_truncation", "immlut": "0x96", "immlut2": "0x1c0", "boolop": "and"}
    cases.append(_boolop_case("and", "boolop_first", "0x96", "0x1c0", "immlut2_9bit_truncation"))
    for tag, a, b, c in (
        ("dual_ab", A_IMM, B_IMM, "%t2"),
        ("dual_ac", A_IMM, "%t1", C_IMM),
        ("dual_bc", "%t0", B_IMM, C_IMM),
        ("triple", A_IMM, B_IMM, C_IMM),
    ):
        coords = {"axis": "discovery", "context": f"multi_immediate_{tag}", "immlut": "0x96", "boolop": "none"}
        cases.append(_simple_case(coords, f"lop3.b32 %r0, {a}, {b}, {c}, 0x96;"))
    return cases


def lop3_expanded_cases() -> list[Case]:
    cases = lop3_syntax_cases()
    cases += _repeated_source_cases()
    cases += _indirect_producer_cases()
    cases.append(_chain_case())
    cases.append(_reuse_diff_operands_case())
    cases.append(_reuse_exact_duplicate_case())
    cases.append(_guard_case())
    cases.append(_template_wide_case())
    cases += _boolop_immlut2_sweep()
    cases += _discovery_cases()
    return cases


# --- negative probes: anchored diagnostics + complement sampling outside the assumed-legal surface ---

def _neg(coords: dict, target: str, reason: str, diagnostic: str, extra_regs: tuple[str, ...] = ()) -> Case:
    return Case(
        "",
        coords,
        parameters=PARAMS1,
        registers=_base_regs(extra_regs),
        preparation=_base_prep(),
        target=(target,),
        observation=(),
        directives=DIRECTIVES,
        expected="reject",
        reason=reason,
        expected_diagnostic=diagnostic,
    )


def lop3_negative_cases() -> list[Case]:
    return [
        _neg({"probe": "type_b64"}, "lop3.b64 %r0, %t0, %t1, %t2, 0x96;", "lop3 has no .b64 form", "Unexpected instruction types specified for 'lop3'"),
        _neg({"probe": "type_u32"}, "lop3.u32 %r0, %t0, %t1, %t2, 0x96;", "lop3 is .b32-only, not signed/unsigned-typed", "Unexpected instruction types specified for 'lop3'"),
        _neg({"probe": "type_f32"}, "lop3.f32 %r0, %t0, %t1, %t2, 0x96;", "lop3 rejects floating-point type spelling", "Unexpected instruction types specified for 'lop3'"),
        _neg({"probe": "type_b16"}, "lop3.b16 %r0, %t0, %t1, %t2, 0x96;", "lop3 has no sub-32-bit width", "Unexpected instruction types specified for 'lop3'"),
        _neg({"probe": "missing_immlut"}, "lop3.b32 %r0, %t0, %t1, %t2;", "immLut is a mandatory 5th argument", "Arguments mismatch for instruction 'lop3'"),
        _neg({"probe": "missing_c_operand"}, "lop3.b32 %r0, %t0, %t1, 0x96;", "dropping c collapses to a 4-argument form ptxas rejects", "Arguments mismatch for instruction 'lop3'"),
        _neg({"probe": "immlut_as_register"}, "lop3.b32 %r0, %t0, %t1, %t2, %t0;", "immLut must be a compile-time literal, not a register", "Arguments mismatch for instruction 'lop3'"),
        _neg({"probe": "five_args_no_boolop"}, "lop3.b32 %r0, %t0, %t1, %t2, 0x96, 0x1;", "a 6th argument requires a BoolOp modifier", "Boolean operation is required for instruction 'lop3'"),
        _neg({"probe": "boolop_xor_illegal"}, "lop3.xor.b32 %r0|%p0, %t0, %t1, %t2, 0x96, 0xc0;", ".xor is not an accepted BoolOp (.and/.or only)", "Illegal operation '.xor' for instruction 'lop3'", (".reg .pred %p0;",)),
        _neg({"probe": "boolop_unknown_modifier"}, "lop3.foo.b32 %r0|%p0, %t0, %t1, %t2, 0x96, 0xc0;", "unrecognized modifier spelling", "Unknown modifier '.foo'", (".reg .pred %p0;",)),
        _neg({"probe": "predicate_output_without_boolop"}, "lop3.b32 %r0|%p0, %t0, %t1, %t2, 0x96;", "predicate destination requires a BoolOp", "Predicate output not allowed for instruction 'lop3'", (".reg .pred %p0;",)),
        _neg({"probe": "boolop_missing_immlut2"}, "lop3.and.b32 %r0|%p0, %t0, %t1, %t2, 0x96;", "BoolOp form needs a 6th argument (immLut2)", "Arguments mismatch for instruction 'lop3'", (".reg .pred %p0;",)),
        _neg({"probe": "operand_negation"}, "lop3.b32 %r0, -%t0, %t1, %t2, 0x96;", "unary negation modifiers are not defined for lop3 sources", "Operand negation not allowed for instruction 'lop3'"),
        # complement sampling outside the assumed-legal surface (P0-2)
        _neg({"probe": "dual_boolop_modifiers"}, "lop3.and.or.b32 %r0|%p0, %t0, %t1, %t2, 0x96, 0xc0;", "stacking two BoolOp modifiers is outside the assumed-legal surface", "Multiple instruction post-operation flags set", (".reg .pred %p0;",)),
        _neg({"probe": "immlut2_as_register"}, "lop3.and.b32 %r0|%p0, %t0, %t1, %t2, 0x96, %t0;", "immLut2 as a register is outside the assumed-legal surface", "Arguments mismatch for instruction 'lop3'", (".reg .pred %p0;",)),
    ]


FACTORS = (
    {"id": "SF.immlut", "levels": list(IMMLUT_LEVELS)},
    {"id": "SF.a_class", "levels": ["reg", "imm", "zero"]},
    {"id": "SF.b_class", "levels": ["reg", "imm", "zero"]},
    {"id": "SF.c_class", "levels": ["reg", "imm", "zero"]},
    {"id": "SF.boolop", "levels": ["none", "and", "or"]},
    {"id": "SF.spelling", "levels": ["boolop_first", "b32_first"]},
    {"id": "CTX.context", "levels": ["baseline", "repeat_ab", "repeat_ac", "repeat_bc", "repeat_abc", "indirect_a", "indirect_b", "indirect_c", "indirect_all", "double_chain", "reuse_lut_diff_operands", "dedup_o3", "guarded", "template_wide", "immlut2_0x00", "immlut2_0xff", "immlut2_0x3c", "immlut2_0x0f", "immlut_9bit_truncation", "immlut_negative_wraparound", "immlut2_9bit_truncation", "multi_immediate_dual_ab", "multi_immediate_dual_ac", "multi_immediate_dual_bc", "multi_immediate_triple"]},
)

SPEC = Spec(
    family="bit",
    opcode="lop3",
    ptx_opcode="lop3",
    target_patterns=("LOP3",),
    factors=FACTORS,
    syntax_cases=lop3_syntax_cases,
    expanded_cases=lop3_expanded_cases,
    negative_cases=lop3_negative_cases,
    empty_target_allowed=lambda _coordinates: False,
)

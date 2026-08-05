#!/usr/bin/env python3
"""Independent experiment definition for (integer) mad on Thor.

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 (`sm_110a`) via standalone probes (see
`../../实验设计.md`):

- mad.lo.{s16,u16,s32,u32,s64,u64} -> single IMAD (16/32-bit) or a 4-instruction
  schoolbook sequence IMAD+IMAD+IMAD.WIDE.U32+IADD3 (64-bit); c is always
  correctly folded in as the accumulate operand.
- mad.hi.{s16,u16} -> IMAD (RZ accumulate) + LEA.HI[.SX32] Rd,Rlo,Rc,0x10
  (the 16-bit hi-half extraction instruction itself performs the "+c" add).
- mad.hi.{s32,u32} (non-.sat) -> a single IMAD.HI[.U32] whose third operand is
  a hardware-materialized zero (HFMA2 at O1-O3, RZ/MOV at O0), NOT the loaded
  c value. This is the flagship discovery of this suite: c is loaded (its
  global-memory read is preserved, so it is not proven dead) but never enters
  the multiply-accumulate. Confirmed architecture-independent (sm_80/90a/
  100a/110a) and confirmed NOT a probe artifact via a multi-consumer variant
  (`hi_accumulate_anchor` case below) where c is also stored independently.
  Contrast: mad.hi.sat.s32 and mad.hi.{s64,u64} DO correctly fold in c (see
  below), so the omission is specific to the plain 32-bit .hi path.
- mad.hi.sat.s32 (the only legal .sat form; ".sat ... [a]pplies only to .s32
  type in .hi mode" per the PTX ISA) -> IMAD.HI(RZ) + IMAD.IADD(+c) +
  PLOP3.LUT x2 (overflow detection) + SEL x2 (clamp to 0x7fffffff/0x80000000).
- mad.hi.{s64,u64} -> a ~12-instruction schoolbook 128-bit high-half combine
  (IMAD.WIDE.U32 chain) that correctly folds in c.
- mad.wide.{s16,u16,s32,u32} -> promoted single IMAD for 16-bit (16x16+32-bit
  c fits in 32 bits, no widen needed) / IMAD.WIDE[.U32]+IADD3+IADD3.X for
  32-bit (widen then add the 64-bit c). mad.wide.{s64,u64} is REJECTED
  ("Unexpected instruction types specified for 'mad.wide'" / "Arguments
  mismatch") -- .wide is only defined for 16- and 32-bit integer types.
- .sat is illegal everywhere except .hi.s32: mad.lo.sat.* -> "Illegal
  modifier '.sat' for instruction 'mad.lo'"; mad.wide.sat.s32 -> "Arguments
  mismatch for instruction 'mad.wide'"; mad.hi.sat.<non-s32> -> "Modifier
  '.sat' does not apply to '.<type>' type". mad.lo.f32 (float mixed into an
  integer-only mode) -> "Unexpected instruction types specified for
  'mad.lo'".
- Baseline scaffold (param load via .u64 pointer + ld.global operands +
  direct st.global result, no xor aggregator, no address arithmetic) was
  compiled O0-O3 with the mad line removed and produced ZERO "IMAD"/"LEA.HI"
  hits at every optimization level, including with immediate result values
  0/1/-1/0x7fffffff/0x12345678 standing in for the mad result. No pattern
  narrowing or optimization-level narrowing was required.
- Identity-element folding (found while building this suite, not predicted
  up front): mad.lo.s32 with the multiplicand slot (a or b) equal to an
  immediate 0/1/-1, or with a*b fully constant (both slots immediate), is
  algebraically simplified away at O1-O3 -- IMAD never appears. a=0 folds to
  a bare copy of c; a=+-1 folds to IADD3(+-b, c); a fully-constant product
  folds to IADD3(with the constant product) or, if the whole expression is
  constant, a MOV/HFMA2 immediate materialization (register c's load can be
  eliminated too, e.g. b=0 makes a's load dead). O0 always still emits a
  literal IMAD (no algebraic simplification at O0). These coordinates are
  registered in `empty_target_allowed` below rather than folded into
  target_patterns, because widening the pattern to catch IADD3/MOV would
  blur mad's own attribution with add's/mov's.
"""

from suite_runtime import Case, Spec

PARAMS = (".param .u64 p_a", ".param .u64 p_b", ".param .u64 p_c", ".param .u64 p_out")

LO_HI_TYPES = ("s16", "u16", "s32", "u32", "s64", "u64")
WIDE_TYPES = ("s16", "u16", "s32", "u32")
WIDE_RESULT_TYPE = {"s16": "s32", "u16": "u32", "s32": "s64", "u32": "u64"}

IMM_LEVELS = (("zero", "0"), ("one", "1"), ("negone", "-1"), ("maxint", "0x7fffffff"), ("big", "0x12345678"))


def _c_type(mode: str, typ: str) -> str:
    return WIDE_RESULT_TYPE[typ] if mode == "wide" else typ


def _mad_line(mode: str, typ: str, sat: bool, a: str = "%a", b: str = "%b", c: str = "%c", d: str = "%d", guard: str = "") -> str:
    sat_tok = ".sat" if sat else ""
    return f"{guard}mad.{mode}{sat_tok}.{typ} {d}, {a}, {b}, {c};"


def _matrix_case(mode: str, typ: str, sat: bool = False) -> Case:
    ct = _c_type(mode, typ)
    coords = {"mode": mode, "type": typ, "sat": sat, "operand_kind": "reg_reg_reg", "context": "baseline"}
    regs = (".reg .b64 %pa,%pb,%pc,%pout;", f".reg .{typ} %a,%b;", f".reg .{ct} %c,%d;")
    prep = (
        "ld.param.u64 %pa,[p_a];", "ld.param.u64 %pb,[p_b];", "ld.param.u64 %pc,[p_c];", "ld.param.u64 %pout,[p_out];",
        f"ld.global.{typ} %a,[%pa];", f"ld.global.{typ} %b,[%pb];", f"ld.global.{ct} %c,[%pc];",
    )
    target = (_mad_line(mode, typ, sat),)
    obs = (f"st.global.{ct} [%pout], %d;",)
    return Case("", coords, parameters=PARAMS, registers=regs, preparation=prep, target=target, observation=obs)


def mode_type_matrix() -> list[Case]:
    cases = [_matrix_case("lo", typ) for typ in LO_HI_TYPES]
    cases += [_matrix_case("hi", typ) for typ in LO_HI_TYPES]
    cases.append(_matrix_case("hi", "s32", sat=True))
    cases += [_matrix_case("wide", typ) for typ in WIDE_TYPES]
    return cases


def _operand_kind_case(kinds: dict, imms: dict, label: str) -> Case:
    mode, typ = "lo", "s32"
    operand_types = {"a": typ, "b": typ, "c": typ}
    regs = [".reg .b64 %pa,%pb,%pc,%pout;"]
    prep = ["ld.param.u64 %pa,[p_a];", "ld.param.u64 %pb,[p_b];", "ld.param.u64 %pc,[p_c];", "ld.param.u64 %pout,[p_out];"]
    operands = {}
    for slot in ("a", "b", "c"):
        if kinds[slot] == "reg":
            regs.append(f".reg .{operand_types[slot]} %{slot};")
            prep.append(f"ld.global.{operand_types[slot]} %{slot},[%p{slot}];")
            operands[slot] = f"%{slot}"
        else:
            operands[slot] = imms[slot]
    regs.append(f".reg .{typ} %d;")
    coords = {"mode": mode, "type": typ, "sat": False, "operand_kind": label, "context": "baseline"}
    target = (f"mad.{mode}.{typ} %d, {operands['a']}, {operands['b']}, {operands['c']};",)
    obs = (f"st.global.{typ} [%pout], %d;",)
    return Case("", coords, parameters=PARAMS, registers=tuple(regs), preparation=tuple(prep), target=target, observation=obs)


def operand_kind_cases() -> list[Case]:
    cases = []
    for slot in ("a", "b", "c"):
        for level_name, level_val in IMM_LEVELS:
            kinds = {"a": "reg", "b": "reg", "c": "reg"}
            kinds[slot] = "imm"
            cases.append(_operand_kind_case(kinds, {slot: level_val}, f"{slot}_imm_{level_name}"))
    # multi-slot immediate combinations (P0-3: not single-factor only)
    cases.append(_operand_kind_case({"a": "imm", "b": "imm", "c": "reg"}, {"a": "0x7fffffff", "b": "-1"}, "ab_imm_combo"))
    cases.append(_operand_kind_case({"a": "reg", "b": "imm", "c": "imm"}, {"b": "0", "c": "0x7fffffff"}, "bc_imm_combo"))
    cases.append(_operand_kind_case({"a": "imm", "b": "imm", "c": "imm"}, {"a": "1", "b": "1", "c": "1"}, "abc_imm_all"))
    return cases


def mad_syntax_cases() -> list[Case]:
    return mode_type_matrix() + operand_kind_cases()


# --------------------------------------------------------------- expanded

def _producer_indirect_case(slot: str) -> Case:
    regs = [".reg .b64 %pa,%pb,%pc,%pout;", ".reg .s32 %a,%b,%c,%d;", ".reg .s32 %t0;"]
    prep = ["ld.param.u64 %pa,[p_a];", "ld.param.u64 %pb,[p_b];", "ld.param.u64 %pc,[p_c];", "ld.param.u64 %pout,[p_out];"]
    ptrs = {"a": "%pa", "b": "%pb", "c": "%pc"}
    for s, ptr in ptrs.items():
        if s == slot:
            prep.append(f"ld.global.s32 %t0,[{ptr}];")
            prep.append(f"add.s32 %{s}, %t0, 0;")
        else:
            prep.append(f"ld.global.s32 %{s},[{ptr}];")
    coords = {"mode": "lo", "type": "s32", "sat": False, "operand_kind": "reg_reg_reg", "context": f"producer_indirect_{slot}"}
    target = ("mad.lo.s32 %d, %a, %b, %c;",)
    obs = ("st.global.s32 [%pout], %d;",)
    return Case("", coords, parameters=PARAMS, registers=tuple(regs), preparation=tuple(prep), target=target, observation=obs)


def _result_multi_consumer_case() -> Case:
    params = PARAMS + (".param .u64 p_out2",)
    regs = (".reg .b64 %pa,%pb,%pc,%pout,%pout2;", ".reg .s32 %a,%b,%c,%d,%e;")
    prep = (
        "ld.param.u64 %pa,[p_a];", "ld.param.u64 %pb,[p_b];", "ld.param.u64 %pc,[p_c];",
        "ld.param.u64 %pout,[p_out];", "ld.param.u64 %pout2,[p_out2];",
        "ld.global.s32 %a,[%pa];", "ld.global.s32 %b,[%pb];", "ld.global.s32 %c,[%pc];",
    )
    target = ("mad.lo.s32 %d, %a, %b, %c;",)
    obs = ("st.global.s32 [%pout], %d;", "add.s32 %e, %d, 1;", "st.global.s32 [%pout2], %e;")
    coords = {"mode": "lo", "type": "s32", "sat": False, "operand_kind": "reg_reg_reg", "context": "result_multi_consumer"}
    return Case("", coords, parameters=params, registers=regs, preparation=prep, target=target, observation=obs)


def _guard_case() -> Case:
    regs = (".reg .b64 %pa,%pb,%pc,%pout;", ".reg .s32 %a,%b,%c,%d,%t0;", ".reg .pred %p;")
    prep = (
        "ld.param.u64 %pa,[p_a];", "ld.param.u64 %pb,[p_b];", "ld.param.u64 %pc,[p_c];", "ld.param.u64 %pout,[p_out];",
        "ld.global.s32 %a,[%pa];", "ld.global.s32 %b,[%pb];", "ld.global.s32 %c,[%pc];",
        "mov.u32 %t0, %tid.x;", "setp.lt.u32 %p, %t0, 16;",
    )
    target = (_mad_line("lo", "s32", False, guard="@%p "),)
    obs = ("st.global.s32 [%pout], %d;",)
    coords = {"mode": "lo", "type": "s32", "sat": False, "operand_kind": "reg_reg_reg", "context": "guarded"}
    return Case("", coords, parameters=PARAMS, registers=regs, preparation=prep, target=target, observation=obs)


def _template_wide_case() -> Case:
    wide_params = (
        ".param .u32 p_pad0", ".param .u64 p_a", ".param .u64 p_pad1", ".param .u64 p_b",
        ".param .u64 p_c", ".param .u64 p_out", ".param .u32 p_pad2",
    )
    regs = (".reg .b64 %pa,%pb,%pc,%pout;", ".reg .s32 %a,%b,%c,%d;")
    prep = (
        "ld.param.u64 %pa,[p_a];", "ld.param.u64 %pb,[p_b];", "ld.param.u64 %pc,[p_c];", "ld.param.u64 %pout,[p_out];",
        "ld.global.s32 %a,[%pa];", "ld.global.s32 %b,[%pb];", "ld.global.s32 %c,[%pc];",
    )
    target = ("mad.lo.s32 %d, %a, %b, %c;",)
    obs = ("st.global.s32 [%pout], %d;",)
    coords = {"mode": "lo", "type": "s32", "sat": False, "operand_kind": "reg_reg_reg", "context": "template_wide"}
    return Case("", coords, parameters=wide_params, registers=regs, preparation=prep, target=target, observation=obs)


def _dual_mad_case() -> Case:
    params = (
        ".param .u64 p_a", ".param .u64 p_b", ".param .u64 p_c", ".param .u64 p_out",
        ".param .u64 p_a2", ".param .u64 p_b2", ".param .u64 p_c2", ".param .u64 p_out2",
    )
    regs = (".reg .b64 %pa,%pb,%pc,%pa2,%pb2,%pc2,%pout,%pout2;", ".reg .s32 %a,%b,%c,%d,%a2,%b2,%c2,%d2;")
    prep = (
        "ld.param.u64 %pa,[p_a];", "ld.param.u64 %pb,[p_b];", "ld.param.u64 %pc,[p_c];", "ld.param.u64 %pout,[p_out];",
        "ld.param.u64 %pa2,[p_a2];", "ld.param.u64 %pb2,[p_b2];", "ld.param.u64 %pc2,[p_c2];", "ld.param.u64 %pout2,[p_out2];",
        "ld.global.s32 %a,[%pa];", "ld.global.s32 %b,[%pb];", "ld.global.s32 %c,[%pc];",
        "ld.global.s32 %a2,[%pa2];", "ld.global.s32 %b2,[%pb2];", "ld.global.s32 %c2,[%pc2];",
    )
    target = ("mad.lo.s32 %d, %a, %b, %c;", "mad.lo.s32 %d2, %a2, %b2, %c2;")
    obs = ("st.global.s32 [%pout], %d;", "st.global.s32 [%pout2], %d2;")
    coords = {"mode": "lo", "type": "s32", "sat": False, "operand_kind": "reg_reg_reg", "context": "dual_mad_slot_reuse"}
    return Case("", coords, parameters=params, registers=regs, preparation=prep, target=target, observation=obs)


def _hi_accumulate_anchor_case() -> Case:
    """Reproduces the flagship finding inside the suite itself: c is stored
    independently (pout2) so its load cannot be dead-code-eliminated, yet the
    mad.hi.s32 IMAD.HI still receives a materialized zero, not c."""
    params = PARAMS + (".param .u64 p_out2",)
    regs = (".reg .b64 %pa,%pb,%pc,%pout,%pout2;", ".reg .s32 %a,%b,%c,%d;")
    prep = (
        "ld.param.u64 %pa,[p_a];", "ld.param.u64 %pb,[p_b];", "ld.param.u64 %pc,[p_c];",
        "ld.param.u64 %pout,[p_out];", "ld.param.u64 %pout2,[p_out2];",
        "ld.global.s32 %a,[%pa];", "ld.global.s32 %b,[%pb];", "ld.global.s32 %c,[%pc];",
    )
    target = ("mad.hi.s32 %d, %a, %b, %c;",)
    obs = ("st.global.s32 [%pout], %d;", "st.global.s32 [%pout2], %c;")
    coords = {"mode": "hi", "type": "s32", "sat": False, "operand_kind": "reg_reg_reg", "context": "hi_accumulate_anchor"}
    return Case("", coords, parameters=params, registers=regs, preparation=prep, target=target, observation=obs)


def mad_expanded_cases() -> list[Case]:
    cases = mad_syntax_cases()
    cases += [_producer_indirect_case(slot) for slot in ("a", "b", "c")]
    cases.append(_result_multi_consumer_case())
    cases.append(_guard_case())
    cases.append(_template_wide_case())
    cases.append(_dual_mad_case())
    cases.append(_hi_accumulate_anchor_case())
    return cases


# --------------------------------------------------------------- negative

def mad_negative_cases() -> list[Case]:
    def probe(typ: str, mad_line: str, coords_extra: dict, reason: str, diagnostic: str) -> Case:
        regs = (".reg .b64 %pa,%pb,%pc,%pout;", f".reg .{typ} %a,%b,%c,%d;")
        prep = (
            "ld.param.u64 %pa,[p_a];", "ld.param.u64 %pb,[p_b];", "ld.param.u64 %pc,[p_c];", "ld.param.u64 %pout,[p_out];",
            f"ld.global.{typ} %a,[%pa];", f"ld.global.{typ} %b,[%pb];", f"ld.global.{typ} %c,[%pc];",
        )
        target = (mad_line,)
        obs = (f"st.global.{typ} [%pout], %d;",)
        coords = {"probe": reason, **coords_extra}
        return Case("", coords, parameters=PARAMS, registers=regs, preparation=prep, target=target, observation=obs, expected="reject", reason=reason, expected_diagnostic=diagnostic)

    return [
        probe("s64", "mad.wide.s64 %d, %a, %b, %c;", {"mode": "wide", "type": "s64"},
              "wide is only defined for 16- and 32-bit integer types", "Unexpected instruction types specified for 'mad.wide'"),
        probe("u64", "mad.wide.u64 %d, %a, %b, %c;", {"mode": "wide", "type": "u64"},
              "wide is only defined for 16- and 32-bit integer types (unsigned)", "Unexpected instruction types specified for 'mad.wide'"),
        probe("s32", "mad.lo.sat.s32 %d, %a, %b, %c;", {"mode": "lo", "type": "s32", "sat": True},
              "sat is illegal on mad.lo (only mad.hi.s32 accepts sat)", "Illegal modifier '.sat' for instruction 'mad.lo'"),
        probe("s32", "mad.wide.sat.s32 %d, %a, %b, %c;", {"mode": "wide", "type": "s32", "sat": True},
              "sat is illegal on mad.wide", "Arguments mismatch for instruction 'mad.wide'"),
        probe("u32", "mad.hi.sat.u32 %d, %a, %b, %c;", {"mode": "hi", "type": "u32", "sat": True},
              "sat applies only to .s32 type in .hi mode, not .u32", "Modifier '.sat' does not apply to '.u32' type"),
        probe("s64", "mad.hi.sat.s64 %d, %a, %b, %c;", {"mode": "hi", "type": "s64", "sat": True},
              "sat applies only to .s32 type in .hi mode, not .s64", "Modifier '.sat' does not apply to '.s64' type"),
        probe("f32", "mad.lo.f32 %d, %a, %b, %c;", {"mode": "lo", "type": "f32"},
              "mad.lo/.hi/.wide are integer-only; f32 uses plain mad.rnd.f32 with no mode token", "Unexpected instruction types specified for 'mad.lo'"),
        # complement sampling outside the assumed-legal surface (P0-2): probe
        # narrower/other type combinations of .sat that were NOT part of the
        # "predicted illegal" set above, to catch a mis-drawn legal boundary.
        probe("s16", "mad.hi.sat.s16 %d, %a, %b, %c;", {"mode": "hi", "type": "s16", "sat": True},
              "complement sample: sat might plausibly scale to narrower signed ints, does not", "Modifier '.sat' does not apply to '.s16' type"),
        probe("u64", "mad.lo.sat.u64 %d, %a, %b, %c;", {"mode": "lo", "type": "u64", "sat": True},
              "complement sample: sat+lo entirely, on the widest unsigned type", "Illegal modifier '.sat' for instruction 'mad.lo'"),
    ]


FACTORS = (
    {"id": "SF.mode", "levels": ["lo", "hi", "wide"]},
    {"id": "SF.type", "levels": ["s16", "u16", "s32", "u32", "s64", "u64", "f32"]},
    {"id": "SF.sat", "levels": [False, True]},
    {"id": "SF.operand_kind", "levels": ["reg_reg_reg", "a_imm_*", "b_imm_*", "c_imm_*", "combo"]},
    {"id": "CTX.context", "levels": [
        "baseline", "producer_indirect_a", "producer_indirect_b", "producer_indirect_c",
        "result_multi_consumer", "guarded", "template_wide", "dual_mad_slot_reuse", "hi_accumulate_anchor",
    ]},
)

# Identity-element algebraic folding (O1-O3 only; see module docstring):
# a or b bound to an immediate 0/+-1 lets ptxas rewrite the multiply away
# (copy / IADD3), and a fully-constant a*b product collapses the whole
# expression to a constant materialization. None of these leave an
# IMAD/LEA.HI behind, so they are legal-but-target-eliminated coordinates.
_FOLDING_OPERAND_KINDS = frozenset({
    "a_imm_zero", "a_imm_one", "a_imm_negone",
    "b_imm_zero", "b_imm_one", "b_imm_negone",
    "ab_imm_combo", "bc_imm_combo", "abc_imm_all",
})


def mad_empty_target_allowed(coordinates: dict) -> bool:
    return coordinates.get("operand_kind") in _FOLDING_OPERAND_KINDS


SPEC = Spec(
    family="int",
    opcode="mad",
    ptx_opcode="mad",
    target_patterns=("IMAD", "LEA.HI"),
    factors=FACTORS,
    syntax_cases=mad_syntax_cases,
    expanded_cases=mad_expanded_cases,
    negative_cases=mad_negative_cases,
    empty_target_allowed=mad_empty_target_allowed,
)

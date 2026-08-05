#!/usr/bin/env python3
"""Independent experiment definition for dp4a on Thor.

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 (`sm_110a`): `dp4a.atype.btype d, a, b, c;` with
atype/btype in {.u32, .s32} (four sign combinations) lowers to
`IDP.4A.{U8,S8}.{U8,S8} d, a, b, c` -- the PTX-level u32/s32 keyword
describes how the four packed bytes inside the 32-bit operand are
interpreted, not the register width. The `b` operand and the `c`
accumulator both accept an immediate: at O0 the immediate is
materialized into a GPR via MOV; at O3 an immediate `b` is routed
through a uniform register (`UR`, e.g. `IDP.4A.U8.U8 R9, R2, UR6, R5`)
while an immediate `c` stays a plain GPR (`IDP.4A.U8.U8 R9, R2, R5, R9`)
-- confirmed asymmetry between the two immediate-capable slots. A
guard predicate does not attach to `IDP.4A` itself at either O0 or O3;
ptxas computes the dot product unconditionally and resolves the guard
with a `SEL` on the result (same pattern documented for `cp.async` in
`02_tma/实验设计.md`).

Falsified during calibration (recorded, not assumed): `cvt.pack`-style
2-operand "no c" packing does not exist for dp4a; every legal form
takes exactly four operands. `.sat` is an illegal modifier for dp4a
(diagnostic: `Illegal modifier '.sat' for instruction 'dp4a'`) even
though dp4a is a saturating-adjacent INT8 primitive in spirit -- there
is no saturation control at the PTX syntax level.
"""

from suite_runtime import Case, Spec

SIGNATURES = (("u32", "u32"), ("s32", "s32"), ("u32", "s32"), ("s32", "u32"))
PARAMS = (".param .u64 p_a", ".param .u64 p_b", ".param .u64 p_c", ".param .u64 p_out")
DIRECTIVES = (".reqntid 128",)
B_IMM = "0x01020304"
C_IMM = "7"


def _instr(atype: str, btype: str, a: str = "%a", b: str = "%b", c: str = "%c", d: str = "%d", guard: str = "") -> str:
    return f"{guard}dp4a.{atype}.{btype} {d}, {a}, {b}, {c};"


def _base_case(atype: str, btype: str, b_class: str = "reg", c_source: str = "reg", context: str = "baseline") -> Case:
    coords = {"atype": atype, "btype": btype, "b_class": b_class, "c_source": c_source, "context": context}
    scalar_regs = ["%a", "%d"]
    prep = [
        "ld.param.u64 %rd_a, [p_a];",
        "ld.param.u64 %rd_b, [p_b];",
        "ld.param.u64 %rd_c, [p_c];",
        "ld.param.u64 %rd_out, [p_out];",
        "ld.global.s32 %a, [%rd_a];",
    ]
    if b_class == "reg":
        scalar_regs.append("%b")
        prep.append("ld.global.s32 %b, [%rd_b];")
        b_operand = "%b"
    else:
        b_operand = B_IMM
    if c_source == "reg":
        scalar_regs.append("%c")
        prep.append("ld.global.s32 %c, [%rd_c];")
        c_operand = "%c"
    else:
        c_operand = C_IMM
    reg_decls = (".reg .u64 %rd_a, %rd_b, %rd_c, %rd_out;", ".reg .s32 " + ", ".join(sorted(set(scalar_regs))) + ";")
    target = (_instr(atype, btype, b=b_operand, c=c_operand),)
    observation = ("st.global.s32 [%rd_out], %d;",)
    return Case("", coords, parameters=PARAMS, registers=reg_decls, preparation=tuple(prep), target=target, observation=observation, directives=DIRECTIVES)


def dp4a_syntax_cases() -> list[Case]:
    cases = []
    # SF.atype x SF.btype full factorial, b and c both register-sourced (baseline)
    for atype, btype in SIGNATURES:
        cases.append(_base_case(atype, btype))
    # SF.b_class: b as immediate, across all four signatures
    for atype, btype in SIGNATURES:
        cases.append(_base_case(atype, btype, b_class="imm", context="b_imm"))
    # SF.c_source: c (accumulator) as immediate, across all four signatures
    for atype, btype in SIGNATURES:
        cases.append(_base_case(atype, btype, c_source="imm", context="c_imm"))
    # P0-3: calibrated dual-modifier combination (b and c both immediate at once)
    cases.append(_base_case("s32", "s32", b_class="imm", c_source="imm", context="dual_imm"))
    cases.append(_base_case("u32", "s32", b_class="imm", c_source="imm", context="dual_imm"))
    return cases


def _context_case(context: str, registers_extra: tuple[str, ...], preparation_extra: tuple[str, ...], target: tuple[str, ...], coords_over: dict | None = None, parameters: tuple[str, ...] = PARAMS, observation: tuple[str, ...] = ("st.global.s32 [%rd_out], %d;",)) -> Case:
    coords = {"atype": "u32", "btype": "u32", "b_class": "reg", "c_source": "reg", "context": context}
    if coords_over:
        coords.update(coords_over)
    regs = (".reg .u64 %rd_a, %rd_b, %rd_c, %rd_out;", ".reg .s32 %a, %b, %c, %d;", *registers_extra)
    prep = (
        "ld.param.u64 %rd_a, [p_a];",
        "ld.param.u64 %rd_b, [p_b];",
        "ld.param.u64 %rd_c, [p_c];",
        "ld.param.u64 %rd_out, [p_out];",
        "ld.global.s32 %a, [%rd_a];",
        "ld.global.s32 %b, [%rd_b];",
        "ld.global.s32 %c, [%rd_c];",
        *preparation_extra,
    )
    return Case("", coords, parameters=parameters, registers=regs, preparation=prep, target=target, observation=observation, directives=DIRECTIVES)


def dp4a_expanded_cases() -> list[Case]:
    cases = dp4a_syntax_cases()

    # CTX.a_indirect: a is not the direct load result but a tid-derived, non-foldable transform (P1-2)
    cases.append(_context_case("a_indirect", (".reg .b32 %t0;",), ("mov.u32 %t0, %tid.x;", "xor.b32 %a, %a, %t0;"), (_instr("u32", "u32"),)))
    # CTX.b_indirect: same treatment on the b operand
    cases.append(_context_case("b_indirect", (".reg .b32 %t0;",), ("mov.u32 %t0, %tid.x;", "xor.b32 %b, %b, %t0;"), (_instr("u32", "u32"),)))
    # CTX.c_indirect: same treatment on the accumulator (distinguishes accumulator-path rematerialization from operand-path)
    cases.append(_context_case("c_indirect", (".reg .b32 %t0;",), ("mov.u32 %t0, %tid.x;", "xor.b32 %c, %c, %t0;"), (_instr("u32", "u32"),)))

    # CTX.guarded: predicated issue (calibrated: IDP.4A executes unconditionally, guard resolved via SEL post-hoc)
    cases.append(_context_case("guarded", (".reg .b32 %t0;", ".reg .pred %p;"), ("mov.u32 %t0, %tid.x;", "setp.lt.u32 %p, %t0, 16;"), (_instr("u32", "u32", guard="@%p "),)))

    # CTX.template_wide: padded kernel signature moves const-bank offsets (P1-1)
    wide_params = (".param .u32 p_pad0", ".param .u64 p_a", ".param .u64 p_pad1", ".param .u64 p_b", ".param .u64 p_c", ".param .u64 p_out", ".param .u32 p_pad2")
    cases.append(_context_case("template_wide", (), (), (_instr("u32", "u32"),), parameters=wide_params))

    # CTX.overlap_dc: destination register aliases the accumulator operand (d == c)
    cases.append(_context_case("overlap_dc", (), (), ("dp4a.u32.u32 %c, %a, %b, %c;",), observation=("st.global.s32 [%rd_out], %c;",)))

    # CTX.chain_depth_2: two dp4a instructions with the accumulator carried serially (P0-1/P0-3 sequence axis)
    chain2_target = ("dp4a.u32.u32 %d, %a, %b, %c;", "dp4a.u32.u32 %d, %b, %a, %d;")
    cases.append(_context_case("chain_depth_2", (), (), chain2_target, coords_over={"c_source": "chain"}))

    # CTX.chain_depth_4: four dp4a instructions serially accumulating (deeper dependency chain than chain_depth_2)
    chain4_target = (
        "dp4a.u32.u32 %d, %a, %b, %c;",
        "dp4a.u32.u32 %d, %b, %a, %d;",
        "dp4a.u32.u32 %d, %a, %c, %d;",
        "dp4a.u32.u32 %d, %c, %b, %d;",
    )
    cases.append(_context_case("chain_depth_4", (), (), chain4_target, coords_over={"c_source": "chain"}))

    # CTX.chain_from_imm: chain whose first accumulator is an immediate rather than a loaded register
    chain_imm_target = ("dp4a.u32.u32 %d, %a, %b, 0;", "dp4a.u32.u32 %d, %b, %a, %d;")
    cases.append(_context_case("chain_from_imm", (), (), chain_imm_target, coords_over={"c_source": "chain", "context": "chain_from_imm"}))

    # CTX.parallel_2: two independent dp4a (disjoint operands) reduced through xor before the store consumer;
    # guards against the O3-eliminates-dead-target pitfall documented in the shared suite guide.
    parallel_regs = (".reg .u64 %rd_a2, %rd_b2, %rd_c2;", ".reg .s32 %a2, %b2, %c2, %d2, %t0;")
    parallel_params = (".param .u64 p_a", ".param .u64 p_b", ".param .u64 p_c", ".param .u64 p_a2", ".param .u64 p_b2", ".param .u64 p_c2", ".param .u64 p_out")
    parallel_prep = (
        "ld.param.u64 %rd_a, [p_a];",
        "ld.param.u64 %rd_b, [p_b];",
        "ld.param.u64 %rd_c, [p_c];",
        "ld.param.u64 %rd_a2, [p_a2];",
        "ld.param.u64 %rd_b2, [p_b2];",
        "ld.param.u64 %rd_c2, [p_c2];",
        "ld.param.u64 %rd_out, [p_out];",
        "ld.global.s32 %a, [%rd_a];",
        "ld.global.s32 %b, [%rd_b];",
        "ld.global.s32 %c, [%rd_c];",
        "ld.global.s32 %a2, [%rd_a2];",
        "ld.global.s32 %b2, [%rd_b2];",
        "ld.global.s32 %c2, [%rd_c2];",
    )
    parallel_target = ("dp4a.u32.u32 %d, %a, %b, %c;", "dp4a.s32.s32 %d2, %a2, %b2, %c2;")
    parallel_observation = ("xor.b32 %t0, %d, %d2;", "st.global.s32 [%rd_out], %t0;")
    parallel_coords = {"atype": "mixed", "btype": "mixed", "b_class": "reg", "c_source": "reg", "context": "parallel_2"}
    cases.append(Case("", parallel_coords, parameters=parallel_params, registers=(".reg .u64 %rd_a, %rd_b, %rd_c, %rd_out;", ".reg .s32 %a, %b, %c, %d;", *parallel_regs), preparation=parallel_prep, target=parallel_target, observation=parallel_observation, directives=DIRECTIVES))

    # CTX.edge_immediate: b as a full-width immediate whose top bit is set (sign-pattern edge for a signed signature)
    cases.append(_context_case("edge_immediate", (), (), (_instr("s32", "s32", b="0xFF010203"),), coords_over={"atype": "s32", "btype": "s32", "b_class": "imm", "context": "edge_immediate"}))

    # CTX.combo_indirect_dual_imm: P0-3 combination of dual-immediate operands with a non-foldable a producer
    combo_target = (_instr("s32", "s32", b=B_IMM, c=C_IMM),)
    cases.append(_context_case("combo_indirect_dual_imm", (".reg .b32 %t0;",), ("mov.u32 %t0, %tid.x;", "xor.b32 %a, %a, %t0;"), combo_target, coords_over={"atype": "s32", "btype": "s32", "b_class": "imm", "c_source": "imm", "context": "combo_indirect_dual_imm"}))

    return cases


def _negative(coords: dict, target: str, reason: str, diagnostic: str) -> Case:
    return Case(
        "",
        coords,
        parameters=PARAMS,
        registers=(".reg .u64 %rd_a, %rd_b, %rd_c, %rd_out;", ".reg .s32 %a, %b, %c, %d;", ".reg .f32 %f;", ".reg .s16 %h;"),
        preparation=(
            "ld.param.u64 %rd_a, [p_a];",
            "ld.param.u64 %rd_b, [p_b];",
            "ld.param.u64 %rd_c, [p_c];",
            "ld.param.u64 %rd_out, [p_out];",
            "ld.global.s32 %a, [%rd_a];",
            "ld.global.s32 %b, [%rd_b];",
            "ld.global.s32 %c, [%rd_c];",
            "ld.global.f32 %f, [%rd_a];",
            "ld.global.s16 %h, [%rd_a];",
        ),
        target=(target,),
        observation=(),
        directives=DIRECTIVES,
        expected="reject",
        reason=reason,
        expected_diagnostic=diagnostic,
    )


def dp4a_negative_cases() -> list[Case]:
    return [
        _negative({"probe": "illegal_signature_u16"}, "dp4a.u16.u32 %d, %a, %b, %c;", "atype/btype must each be u32 or s32; u16 is not a valid dp4a type keyword", "Unexpected instruction types specified for 'dp4a'"),
        _negative({"probe": "illegal_signature_b32"}, "dp4a.b32.b32 %d, %a, %b, %c;", "b32 is an untyped register class, not a valid dp4a sign keyword", "Unexpected instruction types specified for 'dp4a'"),
        _negative({"probe": "single_type_only"}, "dp4a.u32 %d, %a, %b, %c;", "dp4a requires both atype and btype; a single type token is incomplete", "Unexpected instruction types specified for 'dp4a'"),
        _negative({"probe": "f32_operand_mixed_in"}, "dp4a.u32.u32 %d, %f, %b, %c;", "an f32-typed operand cannot substitute for the s32 dp4a operand slot", "Arguments mismatch for instruction 'dp4a'"),
        _negative({"probe": "b64_width_operand"}, "dp4a.u32.u32 %d, %rd_a, %b, %c;", "a 64-bit register cannot fill a dp4a 32-bit operand slot", "Arguments mismatch for instruction 'dp4a'"),
        _negative({"probe": "s16_width_operand"}, "dp4a.u32.u32 %d, %h, %b, %c;", "a 16-bit register cannot fill a dp4a 32-bit operand slot", "Arguments mismatch for instruction 'dp4a'"),
        _negative({"probe": "illegal_sat_modifier"}, "dp4a.sat.u32.u32 %d, %a, %b, %c;", "dp4a has no saturation control at the PTX syntax level", "Illegal modifier '.sat' for instruction 'dp4a'"),
        _negative({"probe": "missing_operand"}, "dp4a.u32.u32 %d, %a, %b;", "dp4a always takes exactly four operands; there is no 3-operand form", "Arguments mismatch for instruction 'dp4a'"),
        # complement sampling outside the core signature/width assumptions (P0-2)
        _negative({"probe": "extra_operand"}, "dp4a.u32.u32 %d, %a, %b, %c, %c;", "a fifth operand is not accepted by any calibrated dp4a form", "Arguments mismatch for instruction 'dp4a'"),
        _negative({"probe": "double_dot_modifier"}, "dp4a.lo.u32.u32 %d, %a, %b, %c;", "dp4a has no .lo/.hi mode selector (that axis belongs to dp2a)", "Comparison qualifier is not allowed for instruction 'dp4a'"),
    ]


FACTORS = (
    {"id": "SF.atype", "levels": ["u32", "s32"]},
    {"id": "SF.btype", "levels": ["u32", "s32"]},
    {"id": "SF.b_class", "levels": ["reg", "imm"]},
    {"id": "SF.c_source", "levels": ["reg", "imm", "chain"]},
    {"id": "CTX.context", "levels": ["baseline", "b_imm", "c_imm", "dual_imm", "a_indirect", "b_indirect", "c_indirect", "guarded", "template_wide", "overlap_dc", "chain_depth_2", "chain_depth_4", "chain_from_imm", "parallel_2", "edge_immediate", "combo_indirect_dual_imm"]},
)

SPEC = Spec(
    family="quant",
    opcode="dp4a",
    ptx_opcode="dp4a",
    target_patterns=("IDP.4A",),
    factors=FACTORS,
    syntax_cases=dp4a_syntax_cases,
    expanded_cases=dp4a_expanded_cases,
    negative_cases=dp4a_negative_cases,
    empty_target_allowed=lambda _coordinates: False,
)

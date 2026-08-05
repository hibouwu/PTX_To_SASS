#!/usr/bin/env python3
"""Independent experiment definition for fma (F16/F16x2) on Thor.

Calibrated against ptxas V13.0.88 / nvdisasm V13.0.85 (`sm_110a`, PTX 9.0):
`fma.rn{.ftz}{.sat}.f16` and the `.f16x2` twin always lower to `HFMA2`;
scalar operands always carry the `.H0_H0` selector on all three sources,
packed operands never do. `.rn` is the only legal rounding token and never
appears in the SASS mnemonic (omitting `.rnd` is rejected: "Rounding
modifier required"; `.rz`/`.rm`/`.rp` are rejected: "Illegal rounding
modifier"). `.ftz` -> `.FTZ`, `.sat` -> `.SAT`, independently or combined.
Modifier order in the PTX text is not significant (`.ftz.rn` parses the
same as `.rn.ftz`). `neg.f16`/`abs.f16` feeding an fma operand fold into
that operand's sign/abs bits in the *same* HFMA2 at O3 (no separate
HADD2); at O0 the neg/abs still materializes via its own HADD2 first.
Immediate operands are always rejected ("Arguments mismatch") -- an f16
constant must be materialized with `mov.b16 %r, 0x3C00;` first. Packing two
independently-valued f16 lanes into one `.b32` f16x2 register is done with
`mov.b32 %packed, {%lo, %hi};` (lowers to `PRMT`) or by loading a pre-packed
32-bit value directly.
"""

from suite_runtime import Case, Spec

PARAMS = (".param .u64 p_a", ".param .u64 p_b", ".param .u64 p_c", ".param .u64 p_out")


def _mods(ftz: bool, sat: bool) -> str:
    text = ".rn"
    if ftz:
        text += ".ftz"
    if sat:
        text += ".sat"
    return text


def _fma_instr(dtype: str, ftz: bool, sat: bool, a: str = "%av", b: str = "%bv", c: str = "%cv", d: str = "%dv") -> str:
    return f"fma{_mods(ftz, sat)}.{dtype} {d}, {a}, {b}, {c};"


def _scalar_registers(extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    return (".reg .b64 %ra, %rb, %rc, %rout;", ".reg .b16 %av, %bv, %cv, %dv;", *extra)


def _scalar_preparation(extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    return (
        "ld.param.b64 %ra, [p_a];",
        "ld.param.b64 %rb, [p_b];",
        "ld.param.b64 %rc, [p_c];",
        "ld.param.b64 %rout, [p_out];",
        "ld.global.b16 %av, [%ra];",
        "ld.global.b16 %bv, [%rb];",
        "ld.global.b16 %cv, [%rc];",
        *extra,
    )


SCALAR_OBSERVATION = ("st.global.b16 [%rout], %dv;",)


def _packed_registers(extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    return (".reg .b64 %ra, %rb, %rc, %rout;", ".reg .b32 %av, %bv, %cv, %dv;", *extra)


def _packed_preparation(extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    return (
        "ld.param.b64 %ra, [p_a];",
        "ld.param.b64 %rb, [p_b];",
        "ld.param.b64 %rc, [p_c];",
        "ld.param.b64 %rout, [p_out];",
        "ld.global.b32 %av, [%ra];",
        "ld.global.b32 %bv, [%rb];",
        "ld.global.b32 %cv, [%rc];",
        *extra,
    )


PACKED_OBSERVATION = ("st.global.b32 [%rout], %dv;",)


def _base_case(dtype: str, ftz: bool, sat: bool, context: str = "baseline") -> Case:
    coords = {"dtype": dtype, "rnd": "rn", "ftz": ftz, "sat": sat, "operand_source": "reg", "context": context}
    if dtype == "f16":
        return Case("", coords, parameters=PARAMS, registers=_scalar_registers(), preparation=_scalar_preparation(), target=(_fma_instr(dtype, ftz, sat),), observation=SCALAR_OBSERVATION)
    return Case("", coords, parameters=PARAMS, registers=_packed_registers(), preparation=_packed_preparation(), target=(_fma_instr(dtype, ftz, sat),), observation=PACKED_OBSERVATION)


def fma_cases() -> list[Case]:
    cases = []
    for dtype in ("f16", "f16x2"):
        for ftz in (False, True):
            for sat in (False, True):
                cases.append(_base_case(dtype, ftz, sat))
    return cases


def fma_expanded() -> list[Case]:
    cases = fma_cases()

    # CTX.lane_asym_pack: the two f16x2 lanes are demonstrably independent
    # (distinct compile-time immediates packed via mov.b32 vector-pack), not a
    # broadcast/degenerate scalar -- the static-experiment analog of the
    # family's "packed lanes must vary independently" completion bar.
    coords = {"dtype": "f16x2", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "packed_producer", "context": "lane_asym_pack"}
    cases.append(Case(
        "", coords, parameters=PARAMS,
        registers=(".reg .b64 %ra, %rc, %rout;", ".reg .b16 %lo, %hi;", ".reg .b32 %av, %cv, %dv;"),
        preparation=(
            "ld.param.b64 %ra, [p_a];",
            "ld.param.b64 %rc, [p_c];",
            "ld.param.b64 %rout, [p_out];",
            "mov.b16 %lo, 0x3C00;",
            "mov.b16 %hi, 0x4000;",
            "mov.b32 %av, {%lo, %hi};",
            "ld.global.b32 %cv, [%rc];",
        ),
        target=(_fma_instr("f16x2", False, False, a="%av", b="%av", c="%cv"),),
        observation=PACKED_OBSERVATION,
    ))

    # CTX.f32_cvt_consumer: does the HFMA2 producer fuse with a cvt.f32.f16
    # consumer? Calibrated: no -- cvt.f32.f16 lowers to a separate
    # HADD2.F32 d, -RZ, src.H0_H0 instruction, never merged into the HFMA2.
    coords = {"dtype": "f16", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "reg", "context": "f32_cvt_consumer"}
    cases.append(Case(
        "", coords, parameters=PARAMS,
        registers=_scalar_registers((".reg .f32 %fv;",)),
        preparation=_scalar_preparation(),
        target=(_fma_instr("f16", False, False), "cvt.f32.f16 %fv, %dv;"),
        observation=("st.global.f32 [%rout], %fv;",),
    ))

    # CTX.fma_chain: two dependent fma (accumulator chain), scalar and packed.
    coords = {"dtype": "f16", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "reg", "context": "fma_chain"}
    cases.append(Case(
        "", coords, parameters=PARAMS,
        registers=_scalar_registers((".reg .b16 %ev;",)),
        preparation=_scalar_preparation(),
        target=(_fma_instr("f16", False, False), _fma_instr("f16", False, False, a="%dv", d="%ev")),
        observation=("st.global.b16 [%rout], %ev;",),
    ))
    coords = {"dtype": "f16x2", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "reg", "context": "fma_chain"}
    cases.append(Case(
        "", coords, parameters=PARAMS,
        registers=_packed_registers((".reg .b32 %ev;",)),
        preparation=_packed_preparation(),
        target=(_fma_instr("f16x2", False, False), _fma_instr("f16x2", False, False, a="%dv", d="%ev")),
        observation=("st.global.b32 [%rout], %ev;",),
    ))

    # CTX.fma_parallel_x3: three independent (non-chained) fma issued back to
    # back -- P0-1-style control/scheduling contrast against fma_chain.
    coords = {"dtype": "f16", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "reg", "context": "fma_parallel_x3"}
    cases.append(Case(
        "", coords, parameters=PARAMS,
        registers=_scalar_registers((".reg .b16 %d1, %d2;",)),
        preparation=_scalar_preparation(),
        target=(_fma_instr("f16", False, False, d="%dv"), _fma_instr("f16", False, False, a="%bv", b="%av", d="%d1"), _fma_instr("f16", False, False, a="%cv", b="%cv", d="%d2")),
        observation=("st.global.b16 [%rout], %dv;", "st.global.b16 [%rout+2], %d1;", "st.global.b16 [%rout+4], %d2;"),
    ))

    # CTX.guarded: predicated issue. Calibrated: HFMA2 always executes
    # unconditionally; the predicate only steers a downstream SEL/PRMT merge
    # (no @P HFMA2 form observed at O0 or O3).
    coords = {"dtype": "f16", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "reg", "context": "guarded"}
    cases.append(Case(
        "", coords, parameters=PARAMS,
        registers=_scalar_registers((".reg .b32 %t0;", ".reg .pred %gp;")),
        preparation=_scalar_preparation(("mov.u32 %t0, %tid.x;", "setp.lt.u32 %gp, %t0, 16;")),
        target=("@%gp " + _fma_instr("f16", False, False),),
        observation=SCALAR_OBSERVATION,
    ))

    # CTX.template_wide: padded/reordered kernel parameter signature (P1-1).
    wide_params = (".param .u32 p_pad0", ".param .u64 p_a", ".param .u64 p_pad1", ".param .u64 p_b", ".param .u64 p_c", ".param .u32 p_pad2", ".param .u64 p_out")
    coords = {"dtype": "f16", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "reg", "context": "template_wide"}
    cases.append(Case("", coords, parameters=wide_params, registers=_scalar_registers(), preparation=_scalar_preparation(), target=(_fma_instr("f16", False, False),), observation=SCALAR_OBSERVATION))

    # CTX.neg_operand_a: neg.f16 feeding the fma multiplicand -- consumer
    # fusion study (P1-2 indirect/non-foldable producer), scalar and packed.
    coords = {"dtype": "f16", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "neg_producer", "context": "neg_operand_a"}
    cases.append(Case(
        "", coords, parameters=PARAMS,
        registers=_scalar_registers((".reg .b16 %nv;",)),
        preparation=_scalar_preparation(("neg.f16 %nv, %av;",)),
        target=(_fma_instr("f16", False, False, a="%nv"),),
        observation=SCALAR_OBSERVATION,
    ))
    coords = {"dtype": "f16x2", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "neg_producer", "context": "neg_operand_a"}
    cases.append(Case(
        "", coords, parameters=PARAMS,
        registers=_packed_registers((".reg .b32 %nv;",)),
        preparation=_packed_preparation(("neg.f16x2 %nv, %av;",)),
        target=(_fma_instr("f16x2", False, False, a="%nv"),),
        observation=PACKED_OBSERVATION,
    ))

    # CTX.abs_operand_a: abs.f16 feeding the fma multiplicand (mirrors neg).
    coords = {"dtype": "f16", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "abs_producer", "context": "abs_operand_a"}
    cases.append(Case(
        "", coords, parameters=PARAMS,
        registers=_scalar_registers((".reg .b16 %nv;",)),
        preparation=_scalar_preparation(("abs.f16 %nv, %av;",)),
        target=(_fma_instr("f16", False, False, a="%nv"),),
        observation=SCALAR_OBSERVATION,
    ))

    # CTX.result_reused: the fma result feeds both a direct store and a
    # second consumer (mul) -- register reuse / multi-use priority context.
    coords = {"dtype": "f16", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "reg", "context": "result_reused"}
    cases.append(Case(
        "", coords, parameters=PARAMS,
        registers=_scalar_registers((".reg .b16 %ev;",)),
        preparation=_scalar_preparation(),
        target=(_fma_instr("f16", False, False),),
        observation=("mul.f16 %ev, %dv, %bv;", "st.global.b16 [%rout], %dv;", "st.global.b16 [%rout+2], %ev;"),
    ))

    # CTX.spelling_modifier_order: calibrated accepted alternate spelling
    # (.ftz before .rn) -- same semantic form, generator must not assume a
    # canonical modifier order.
    coords = {"dtype": "f16", "rnd": "rn", "ftz": True, "sat": False, "operand_source": "reg", "context": "spelling_modifier_order"}
    cases.append(Case("", coords, parameters=PARAMS, registers=_scalar_registers(), preparation=_scalar_preparation(), target=("fma.ftz.rn.f16 %dv, %av, %bv, %cv;",), observation=SCALAR_OBSERVATION))

    # CTX.operand_alias: destination aliases the accumulator operand
    # (in-place accumulate) -- register reuse priority context.
    coords = {"dtype": "f16", "rnd": "rn", "ftz": False, "sat": False, "operand_source": "reg", "context": "operand_alias"}
    cases.append(Case("", coords, parameters=PARAMS, registers=_scalar_registers(), preparation=_scalar_preparation(), target=(_fma_instr("f16", False, False, d="%cv"),), observation=("st.global.b16 [%rout], %cv;",)))

    return cases


def fma_negative() -> list[Case]:
    def probe(coords: dict, target: str, reason: str, diagnostic: str, dtype: str = "f16") -> Case:
        if dtype == "f16":
            return Case("", coords, parameters=PARAMS, registers=_scalar_registers(), preparation=_scalar_preparation(), target=(target,), observation=(), expected="reject", reason=reason, expected_diagnostic=diagnostic)
        return Case("", coords, parameters=PARAMS, registers=_packed_registers(), preparation=_packed_preparation(), target=(target,), observation=(), expected="reject", reason=reason, expected_diagnostic=diagnostic)

    return [
        probe({"probe": "missing_rounding_scalar"}, "fma.f16 %dv, %av, %bv, %cv;", "fma requires an explicit rounding modifier", "Rounding modifier required"),
        probe({"probe": "missing_rounding_packed"}, "fma.f16x2 %dv, %av, %bv, %cv;", "fma requires an explicit rounding modifier (packed)", "Rounding modifier required", dtype="f16x2"),
        probe({"probe": "illegal_rounding_rz"}, "fma.rz.f16 %dv, %av, %bv, %cv;", ".rz is not a legal fma.f16 rounding token", "Illegal rounding modifier"),
        probe({"probe": "illegal_rounding_rm"}, "fma.rm.f16 %dv, %av, %bv, %cv;", ".rm is not a legal fma.f16 rounding token", "Illegal rounding modifier"),
        probe({"probe": "illegal_rounding_rp"}, "fma.rp.f16 %dv, %av, %bv, %cv;", ".rp is not a legal fma.f16 rounding token", "Illegal rounding modifier"),
        probe({"probe": "b16_type"}, "fma.rn.b16 %dv, %av, %bv, %cv;", "fma has no untyped .b16 form", "Unexpected instruction types"),
        probe({"probe": "unknown_neg_modifier"}, "fma.rn.neg.f16 %dv, %av, %bv, %cv;", "fma has no dedicated .neg modifier; negation must come from a separate neg.f16 producer", "Unknown modifier"),
        probe({"probe": "immediate_operand"}, "fma.rn.f16 %dv, 0x3C00, %bv, %cv;", "f16 arithmetic never accepts an immediate source operand", "Arguments mismatch"),
        # complement sampling outside the assumed-legal surface (P0-2)
        probe({"probe": "operand_b_width_mismatch"}, "fma.rn.f16 %dv, %av, %bx32, %cv;", "single-operand width mismatch (b is .b32 in an otherwise-scalar fma.f16)", "Arguments mismatch"),
        probe({"probe": "dest_width_mismatch"}, "fma.rn.ftz.sat.f16 %dx32, %av, %bv, %cv;", "destination-width mismatch (.b32 destination for scalar fma.f16)", "Arguments mismatch"),
    ]


# the two complement-sample probes above need one extra operand register each
def _negative_with_extra() -> list[Case]:
    cases = fma_negative()
    patched = []
    for case in cases:
        if case.coordinates.get("probe") == "operand_b_width_mismatch":
            case = Case(case.label, case.coordinates, case.declarations, case.parameters, _scalar_registers((".reg .b32 %bx32;",)), _scalar_preparation(("ld.global.b32 %bx32, [%rb];",)), case.target, case.observation, case.directives, case.expected, case.reason, case.expected_diagnostic)
        elif case.coordinates.get("probe") == "dest_width_mismatch":
            case = Case(case.label, case.coordinates, case.declarations, case.parameters, _scalar_registers((".reg .b32 %dx32;",)), _scalar_preparation(), case.target, case.observation, case.directives, case.expected, case.reason, case.expected_diagnostic)
        patched.append(case)
    return patched


FACTORS = (
    {"id": "SF.dtype", "levels": ["f16", "f16x2"]},
    {"id": "SF.rnd", "levels": ["rn"]},
    {"id": "SF.ftz", "levels": [False, True]},
    {"id": "SF.sat", "levels": [False, True]},
    {"id": "CTX.operand_source", "levels": ["reg", "packed_producer", "neg_producer", "abs_producer"]},
    {"id": "CTX.context", "levels": ["baseline", "lane_asym_pack", "f32_cvt_consumer", "fma_chain", "fma_parallel_x3", "guarded", "template_wide", "neg_operand_a", "abs_operand_a", "result_reused", "spelling_modifier_order", "operand_alias"]},
)

SPEC = Spec(
    family="f16",
    opcode="fma",
    ptx_opcode="fma",
    target_patterns=("HFMA2",),
    factors=FACTORS,
    syntax_cases=fma_cases,
    expanded_cases=fma_expanded,
    negative_cases=_negative_with_extra,
    empty_target_allowed=lambda _coordinates: False,
)

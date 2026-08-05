#!/usr/bin/env python3
"""Independent experiment definition for fma (F32/F64) on Thor.

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 (`sm_110a`) with throwaway scratchpad probes before this
file was written (see 06_cuda_core_fp/实验设计.md for the full calibration
table). Summary of what calibration established:

- fma.rnd.f32 and fma.rnd.f64 both require an EXPLICIT rounding modifier
  (unlike add/sub/mul, where rnd is optional and defaults to .rn). Omitting
  it is rejected with "Rounding modifier required for instruction 'fma'".
- .rn does not appear in the SASS mnemonic (it is the unmarked/default
  form); .rz/.rm/.rp appear as FFMA.RZ/.RM/.RP or DFMA.RZ/.RM/.RP.
- .ftz and .sat are legal only on the .f32 form; both are rejected on .f64
  with dedicated "Illegal modifier '.ftz'/'.sat' for instruction 'fma'"
  diagnostics. All four rounding modes combine freely with .ftz and/or
  .sat on f32 (FFMA.FTZ.SAT, FFMA.RP.FTZ, etc.).
- PTX does not allow inline operand negation syntax directly inside fma's
  operand list ("fma.rn.f32 d, -a, b, c;" is rejected: "Operand negation
  not allowed for instruction 'fma'"). abs.f32/neg.f32 as a SEPARATE
  producer instruction DOES fold into the consuming FFMA/DFMA as a source
  modifier (|Ra|, -Ra) -- this is the "folded" class, reachable only via a
  real preceding abs/neg PTX instruction, never via direct operand syntax.
- Modifier spelling order is not canonical: "fma.f32.rn", "fma.ftz.rn.f32"
  and "fma.sat.rn.f32" all compile to the identical FFMA as the canonical
  "fma.rn.ftz.sat.f32" spelling -- an assumed-illegal-by-convention form
  that calibration proved legal (P0-2 complement finding, kept as an
  expanded spelling-variant case rather than folded silently into the
  canonical axis).
- fma.rn.f16 / fma.rn.bf16 (packed 16-bit) ARE accepted by ptxas in this
  same opcode -- they lower to HFMA2/HFMA2.BF16_V2, not FFMA/DFMA. That is
  a P0-2 complement-sampling discovery (this task's own review script
  assumed fma.f16 would be rejected here and redirected to 11_half_precision;
  calibration shows it is not rejected, merely out of this suite's
  FFMA/DFMA target scope) and is recorded in the family design doc rather
  than used as a negative anchor.
"""

from suite_runtime import Case, Spec

PARAMS = (".param .u64 p_a", ".param .u64 p_b", ".param .u64 p_c", ".param .u64 p_out")

# f32 / f64 immediate literal encodings, calibrated against the PTX 9.0
# 0f<hex32> / 0d<hex64> literal syntax (probe:lit_check).
IMM = {
    "f32": {
        "zero": "0f00000000",
        "one": "0f3F800000",
        "neg_one": "0fBF800000",
        "half": "0f3F000000",
        "denorm": "0f00000001",
        "large": "0f7F7FFFFF",
    },
    "f64": {
        "zero": "0d0000000000000000",
        "one": "0d3FF0000000000000",
        "neg_one": "0dBFF0000000000000",
        "half": "0d3FE0000000000000",
        "denorm": "0d0000000000000001",
        "large": "0d7FEFFFFFFFFFFFFF",
    },
}
IMM_ORDER = ("zero", "one", "neg_one", "half", "denorm", "large")


def _regs(t: str, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    regs = [
        f".reg .{t} %a, %b, %c, %fo;",
        ".reg .u64 %pa, %pb, %pc, %pout;",
    ]
    regs.extend(extra)
    return tuple(regs)


def _prep(t: str, extra: tuple[str, ...] = (), load_a: bool = True, load_b: bool = True, load_c: bool = True) -> tuple[str, ...]:
    prep = [
        "ld.param.u64 %pa, [p_a];",
        "ld.param.u64 %pb, [p_b];",
        "ld.param.u64 %pc, [p_c];",
        "ld.param.u64 %pout, [p_out];",
    ]
    if load_a:
        prep.append(f"ld.global.{t} %a, [%pa];")
    if load_b:
        prep.append(f"ld.global.{t} %b, [%pb];")
    if load_c:
        prep.append(f"ld.global.{t} %c, [%pc];")
    prep.extend(extra)
    return tuple(prep)


def _mnemonic(t: str, rnd: str, ftz: bool, sat: bool) -> str:
    return f"fma.{rnd}{'.ftz' if ftz else ''}{'.sat' if sat else ''}.{t}"


def _base_case(t: str, rnd: str, ftz: bool, sat: bool, context: str = "baseline") -> Case:
    coords = {"type": t, "rnd": rnd, "ftz": ftz, "sat": sat, "a_class": "reg", "b_class": "reg", "c_class": "reg", "context": context}
    target = f"{_mnemonic(t, rnd, ftz, sat)} %fo, %a, %b, %c;"
    return Case(
        "",
        coords,
        parameters=PARAMS,
        registers=_regs(t),
        preparation=_prep(t),
        target=(target,),
        observation=(f"st.global.{t} [%pout], %fo;",),
    )


def fma_cases() -> list[Case]:
    cases = []
    for rnd in ("rn", "rz", "rm", "rp"):
        for ftz in (False, True):
            for sat in (False, True):
                cases.append(_base_case("f32", rnd, ftz, sat))
    for rnd in ("rn", "rz", "rm", "rp"):
        cases.append(_base_case("f64", rnd, False, False))
    return cases


def _imm_case(t: str, slot: str, val_name: str) -> Case:
    lit = IMM[t][val_name]
    coords = {"type": t, "rnd": "rn", "ftz": False, "sat": False, "a_class": "reg" if slot != "a" else "imm", "b_class": "reg" if slot != "b" else "imm", "c_class": "reg" if slot != "c" else "imm", "context": f"imm_{slot}_{val_name}"}
    operands = {"a": "%a", "b": "%b", "c": "%c"}
    operands[slot] = lit
    load_a, load_b, load_c = slot != "a", slot != "b", slot != "c"
    target = f"{_mnemonic(t, 'rn', False, False)} %fo, {operands['a']}, {operands['b']}, {operands['c']};"
    return Case(
        "",
        coords,
        parameters=PARAMS,
        registers=_regs(t),
        preparation=_prep(t, load_a=load_a, load_b=load_b, load_c=load_c),
        target=(target,),
        observation=(f"st.global.{t} [%pout], %fo;",),
    )


def _fold_case(t: str, variant: str) -> Case:
    # variant in {"neg_a", "abs_a", "neg_abs_a"}: separate abs/neg PTX
    # instruction feeding the fma 'a' operand -- calibrated to fold into
    # the FFMA/DFMA source modifier (|Ra| / -Ra), unlike direct "-%a"
    # operand syntax which ptxas rejects outright.
    ops = []
    if "abs" in variant:
        ops.append(f"abs.{t} %a, %a;")
    if "neg" in variant:
        ops.append(f"neg.{t} %a, %a;")
    coords = {"type": t, "rnd": "rn", "ftz": False, "sat": False, "a_class": "folded", "b_class": "reg", "c_class": "reg", "context": f"fold_{variant}"}
    target = f"{_mnemonic(t, 'rn', False, False)} %fo, %a, %b, %c;"
    return Case(
        "",
        coords,
        parameters=PARAMS,
        registers=_regs(t),
        preparation=_prep(t, extra=tuple(ops)),
        target=(target,),
        observation=(f"st.global.{t} [%pout], %fo;",),
    )


def _indirect_case(t: str, variant: str) -> Case:
    # producer for the 'a' operand is not compile-time foldable: either a
    # tid-derived address (P1-2 non-foldable arithmetic) or a genuine
    # double load through a pointer loaded from memory.
    if variant == "tid_addr":
        shift = "3" if t == "f64" else "2"
        extra_regs = (".reg .u64 %off, %pa2;",)
        prep = ("cvt.u64.u32 %off, %tid.x;", f"shl.b64 %off, %off, {shift};", "add.u64 %pa2, %pa, %off;", f"ld.global.{t} %a, [%pa2];")
        load_a = False
    else:  # ptr_indirect: load a pointer value, then load the operand through it
        extra_regs = (".reg .u64 %pa2;",)
        prep = ("ld.global.u64 %pa2, [%pa];", f"ld.global.{t} %a, [%pa2];")
        load_a = False
    coords = {"type": t, "rnd": "rn", "ftz": False, "sat": False, "a_class": "indirect", "b_class": "reg", "c_class": "reg", "context": f"indirect_{variant}"}
    target = f"{_mnemonic(t, 'rn', False, False)} %fo, %a, %b, %c;"
    return Case(
        "",
        coords,
        parameters=PARAMS,
        registers=_regs(t, extra_regs),
        preparation=_prep(t, extra=prep, load_a=load_a),
        target=(target,),
        observation=(f"st.global.{t} [%pout], %fo;",),
    )


def _chain_case(t: str, depth: int, dependent: bool) -> Case:
    # dependency-chain context: fma feeding fma. Not an async control-word
    # axis (fma has no scoreboard), but this is the ALU analogue of
    # tcgen05-review P0-1 "control bits are a shared scheduling resource":
    # runtime keeps full_instructions (128-bit encoding) for every case, so
    # stall/yield/reuse/barrier control-word differencing between a
    # dependent and an independent chain of the same depth is available
    # without re-running anything.
    mnem = _mnemonic(t, "rn", False, False)
    targets = []
    if dependent:
        targets.append(f"{mnem} %fo, %a, %b, %c;")
        for _ in range(depth - 1):
            targets.append(f"{mnem} %fo, %fo, %b, %c;")
        extra_regs = ()
    else:
        extra_regs = tuple(f".reg .{t} %x{i};" for i in range(depth - 1))
        targets.append(f"{mnem} %fo, %a, %b, %c;")
        for i in range(depth - 1):
            targets.append(f"{mnem} %x{i}, %a, %c, %b;")
        # fold parallel results into the observed value via consumer adds
        # kept out of the target set (they are FADD/DADD, not FFMA/DFMA)
    context = f"chain_depth_{depth}" if dependent else f"chain_parallel_{depth}"
    coords = {"type": t, "rnd": "rn", "ftz": False, "sat": False, "a_class": "reg", "b_class": "reg", "c_class": "reg", "context": context}
    if dependent:
        observation = (f"st.global.{t} [%pout], %fo;",)
    else:
        acc = "%fo"
        obs = []
        for i in range(depth - 1):
            obs.append(f"add.rn.{t} %fo, {acc}, %x{i};")
            acc = "%fo"
        obs.append(f"st.global.{t} [%pout], %fo;")
        observation = tuple(obs)
    return Case(
        "",
        coords,
        parameters=PARAMS,
        registers=_regs(t, extra_regs),
        preparation=_prep(t),
        target=tuple(targets),
        observation=observation,
    )


def _guard_case(t: str) -> Case:
    # calibrated finding: unlike TMA's async UTMALDG (where "@%p" survives as
    # a literal "@!UPx UTMALDG" predicate prefix because the op has a real
    # side effect that must not fire when the guard is false), a guarded
    # fma is pure/side-effect-free, so ptxas if-converts it at EVERY
    # optimization level including O0: FFMA/DFMA executes unconditionally
    # and an FSEL/DSEL picks between the fma result and the untaken path's
    # value before the unconditional store. target_patterns still attribute
    # (FFMA/DFMA is present, just never predicate-prefixed), but a reader
    # must not expect "@P FFMA" in the disassembly here.
    coords = {"type": t, "rnd": "rn", "ftz": False, "sat": False, "a_class": "reg", "b_class": "reg", "c_class": "reg", "context": "guarded"}
    target = f"@%p {_mnemonic(t, 'rn', False, False)} %fo, %a, %b, %c;"
    return Case(
        "",
        coords,
        parameters=PARAMS,
        registers=_regs(t, (".reg .pred %p;", ".reg .u32 %tid0;")),
        preparation=_prep(t, extra=("mov.u32 %tid0, %tid.x;", "setp.lt.u32 %p, %tid0, 16;")),
        target=(target,),
        observation=(f"st.global.{t} [%pout], %fo;",),
    )


def _template_wide_case(t: str) -> Case:
    wide_params = (".param .u32 p_pad0", ".param .u64 p_a", ".param .u32 p_pad1", ".param .u64 p_b", ".param .u64 p_c", ".param .u64 p_out", ".param .u32 p_pad2")
    coords = {"type": t, "rnd": "rn", "ftz": False, "sat": False, "a_class": "reg", "b_class": "reg", "c_class": "reg", "context": "template_wide"}
    target = f"{_mnemonic(t, 'rn', False, False)} %fo, %a, %b, %c;"
    return Case(
        "",
        coords,
        parameters=wide_params,
        registers=_regs(t),
        preparation=_prep(t),
        target=(target,),
        observation=(f"st.global.{t} [%pout], %fo;",),
    )


def _spelling_case() -> Case:
    # calibrated P0-2 complement finding: modifier order is not canonical.
    coords = {"type": "f32", "rnd": "rn", "ftz": False, "sat": False, "a_class": "reg", "b_class": "reg", "c_class": "reg", "context": "spelling_type_before_rnd"}
    return Case(
        "",
        coords,
        parameters=PARAMS,
        registers=_regs("f32"),
        preparation=_prep("f32"),
        target=("fma.f32.rn %fo, %a, %b, %c;",),
        observation=("st.global.f32 [%pout], %fo;",),
    )


def fma_expanded() -> list[Case]:
    cases = fma_cases()
    for t in ("f32", "f64"):
        for slot in ("a", "b", "c"):
            for val_name in IMM_ORDER:
                cases.append(_imm_case(t, slot, val_name))
    for t in ("f32", "f64"):
        for variant in ("neg_a", "abs_a", "neg_abs_a"):
            cases.append(_fold_case(t, variant))
    for t in ("f32", "f64"):
        for variant in ("tid_addr", "ptr_indirect"):
            cases.append(_indirect_case(t, variant))
    for t in ("f32", "f64"):
        cases.append(_chain_case(t, 2, dependent=True))
        cases.append(_chain_case(t, 4, dependent=True))
        cases.append(_chain_case(t, 2, dependent=False))
    for t in ("f32", "f64"):
        cases.append(_guard_case(t))
    for t in ("f32", "f64"):
        cases.append(_template_wide_case(t))
    cases.append(_spelling_case())
    return cases


def fma_negative() -> list[Case]:
    def probe(coords: dict, target: str, reason: str, diagnostic: str, t: str = "f32") -> Case:
        return Case(
            "",
            coords,
            parameters=PARAMS,
            registers=_regs(t),
            preparation=_prep(t),
            target=(target,),
            observation=(),
            expected="reject",
            reason=reason,
            expected_diagnostic=diagnostic,
        )

    def probe_s32(coords: dict, target: str, reason: str, diagnostic: str) -> Case:
        return Case(
            "",
            coords,
            parameters=(".param .u64 p_a", ".param .u64 p_b", ".param .u64 p_c", ".param .u64 p_out"),
            registers=(".reg .s32 %a, %b, %c, %fo;", ".reg .u64 %pa, %pb, %pc, %pout;"),
            preparation=("ld.param.u64 %pa, [p_a];", "ld.param.u64 %pb, [p_b];", "ld.param.u64 %pc, [p_c];", "ld.param.u64 %pout, [p_out];", "ld.global.s32 %a, [%pa];", "ld.global.s32 %b, [%pb];", "ld.global.s32 %c, [%pc];"),
            target=(target,),
            observation=(),
            expected="reject",
            reason=reason,
            expected_diagnostic=diagnostic,
        )

    def probe_mixed(coords: dict, target: str, reason: str, diagnostic: str) -> Case:
        return Case(
            "",
            coords,
            parameters=PARAMS,
            registers=(".reg .f32 %a, %b, %c, %fo;", ".reg .f64 %d;", ".reg .u64 %pa, %pb, %pc, %pout;"),
            preparation=("ld.param.u64 %pa, [p_a];", "ld.param.u64 %pb, [p_b];", "ld.param.u64 %pc, [p_c];", "ld.param.u64 %pout, [p_out];", "ld.global.f32 %a, [%pa];", "ld.global.f32 %b, [%pb];", "ld.global.f32 %c, [%pc];", "ld.global.f64 %d, [%pa];"),
            target=(target,),
            observation=(),
            expected="reject",
            reason=reason,
            expected_diagnostic=diagnostic,
        )

    return [
        probe({"probe": "no_rounding_f32"}, "fma.f32 %fo, %a, %b, %c;", "fma has no default rounding mode, unlike add/sub/mul", "Rounding modifier required for instruction 'fma'"),
        probe({"probe": "ftz_f64"}, "fma.rn.ftz.f64 %fo, %a, %b, %c;", ".ftz is f32-only for fma", "Illegal modifier '.ftz' for instruction 'fma'", t="f64"),
        probe({"probe": "sat_f64"}, "fma.rn.sat.f64 %fo, %a, %b, %c;", ".sat is f32-only for fma", "Illegal modifier '.sat' for instruction 'fma'", t="f64"),
        probe_s32({"probe": "integer_type"}, "fma.rn.s32 %fo, %a, %b, %c;", "fma is float-only; mad is the integer form", "Unexpected instruction types specified for 'fma'"),
        probe({"probe": "direct_operand_negation"}, "fma.rn.f32 %fo, -%a, %b, %c;", "PTX grammar forbids inline operand negation on fma (unlike the folded neg.f32 producer case)", "Operand negation not allowed for instruction 'fma'"),
        probe({"probe": "arity_missing_operand"}, "fma.rn.f32 %fo, %a, %b;", "fma is a 4-operand instruction", "Arguments mismatch for instruction 'fma'"),
        probe_mixed({"probe": "type_mismatch_f64_operand_in_f32"}, "fma.rn.f32 %fo, %d, %b, %c;", "operand type must match the declared instruction type", "Arguments mismatch for instruction 'fma'"),
        probe({"probe": "approx_not_a_rounding_mode"}, "fma.approx.f32 %fo, %a, %b, %c;", "fma has no .approx form (unlike rcp/sqrt/div); ptxas treats it as an unrecognized rounding token", "Rounding modifier required for instruction 'fma'"),
        # complement sampling outside the assumed-legal surface (P0-2)
        probe({"probe": "double_rounding_modifier"}, "fma.rn.rz.f32 %fo, %a, %b, %c;", "stacking two rounding modifiers is outside the assumed grammar", "Multiple rounding modifiers specified"),
        probe({"probe": "missing_type_suffix"}, "fma.rn %fo, %a, %b, %c;", "type suffix is mandatory even though rnd already narrows to float", "Unexpected instruction types specified for 'fma'"),
    ]


FACTORS = (
    {"id": "SF.type", "levels": ["f32", "f64"]},
    {"id": "SF.rnd", "levels": ["rn", "rz", "rm", "rp"]},
    {"id": "SF.ftz", "levels": [False, True]},
    {"id": "SF.sat", "levels": [False, True]},
    {"id": "SF.a_class", "levels": ["reg", "imm", "folded", "indirect"]},
    {"id": "SF.b_class", "levels": ["reg", "imm"]},
    {"id": "SF.c_class", "levels": ["reg", "imm"]},
    {"id": "CTX.context", "levels": ["baseline", "imm_a_zero", "imm_a_one", "imm_a_neg_one", "imm_a_half", "imm_a_denorm", "imm_a_large", "imm_b_zero", "imm_b_one", "imm_b_neg_one", "imm_b_half", "imm_b_denorm", "imm_b_large", "imm_c_zero", "imm_c_one", "imm_c_neg_one", "imm_c_half", "imm_c_denorm", "imm_c_large", "fold_neg_a", "fold_abs_a", "fold_neg_abs_a", "indirect_tid_addr", "indirect_ptr_indirect", "chain_depth_2", "chain_depth_4", "chain_parallel_2", "guarded", "template_wide", "spelling_type_before_rnd"]},
)

SPEC = Spec(
    family="fp",
    opcode="fma",
    ptx_opcode="fma",
    target_patterns=("FFMA", "DFMA"),
    factors=FACTORS,
    syntax_cases=fma_cases,
    expanded_cases=fma_expanded,
    negative_cases=fma_negative,
    empty_target_allowed=lambda _coordinates: False,
)

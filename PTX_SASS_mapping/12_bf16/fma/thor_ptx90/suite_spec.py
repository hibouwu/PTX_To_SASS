#!/usr/bin/env python3
"""Independent experiment definition for fma.bf16 / fma.bf16x2 on Thor.

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 (`sm_110a`) with throwaway scratch probes (not reused from
any other family -- bf16 and f16 do not share conclusions per project
threshold). Headline calibration facts baked into this spec:

- fma is the only bf16 arithmetic opcode in this family that REQUIRES an
  explicit rounding token (`Rounding modifier required for instruction 'fma'`
  when omitted); add/sub/mul/min/max never take an explicit .rz/.rm/.rp and
  reject them outright (`Illegal rounding modifier for instruction '<op>'`).
- fma UNIQUELY accepts .rz/.rm/.rp (add/sub/mul/min/max do not -- verified
  independently). But the two dtypes diverge sharply once accepted:
    * bf16 (scalar) + .rn  -> native HFMA2.BF16_V2 (selector .H0_H0/.H1_H1
      broadcast-pack idiom, since there is no dedicated scalar half unit).
    * bf16 (scalar) + .rz/.rm/.rp -> completely different lowering: the
      operands are each widened to f32 via `HADD2.F32 Rx, -RZ, Ry.HZ_HZ`,
      the fma runs as `FFMA.RZ/RM/RP` in f32, and the result is narrowed
      back with `F2F.F16.F32`. The native packed unit apparently cannot
      express non-RN rounding, so ptxas falls back to software emulation.
    * bf16x2 (packed) + .rn/.rz/.rm/.rp -> ALWAYS the same native
      `HFMA2.BF16_V2` encoding, bit-for-bit identical regardless of which
      rounding token was written in the PTX. The packed path silently
      ignores the rounding request at the static level; only the scalar
      path honors it via emulation. This is a static-only observation, not
      a runtime rounding-correctness claim.
- .ftz and .sat are illegal for fma.bf16/bf16x2 on every rounding path,
  including the emulated .rz/.rm/.rp path (`Illegal modifier '.ftz'/'.sat'
  for instruction 'fma'`) -- the modifier check happens before path
  selection, confirmed as a complement-sampling probe.
- Operand negation/abs modifiers (`-a`, `|a|`) are rejected at parse time
  for fma.bf16 (`Operand negation not allowed for instruction 'fma'` /
  `Parsing error near '|'`) -- there is no PTX-syntax route to fold neg/abs
  into fma's operand slots for this type family.
- `mov.b32 %rd, {%rh0, %rh1};` legally packs two independently-produced
  .b16 halves into one .b32 bf16x2 register -- used here to build
  genuinely lane-asymmetric bf16x2 operands (not a broadcast of one value).
"""

from suite_runtime import Case, Spec

ROUNDINGS = ("rn", "rz", "rm", "rp")

SCALAR_REGS = (".reg .b16 %v0, %v1, %v2, %vd;", ".reg .u64 %out;")
SCALAR_PREP = ("ld.param.u64 %out, [p_out];", "mov.u16 %v0, 0x3F80;", "mov.u16 %v1, 0x4000;", "mov.u16 %v2, 0xBF80;")
SCALAR_OBS = ("st.global.b16 [%out], %vd;",)

X2_REGS = (".reg .b32 %w0, %w1, %w2, %wd;", ".reg .u64 %out;")
X2_PREP = ("ld.param.u64 %out, [p_out];", "mov.b32 %w0, 0x40003F80;", "mov.b32 %w1, 0xBF803F80;", "mov.b32 %w2, 0x3F803F80;")
X2_OBS = ("st.global.b32 [%out], %wd;",)

PARAMS = (".param .u64 p_out",)
PARAMS_IN = (".param .u64 p_out", ".param .u64 p_in")


def _scalar_fma(rnd: str, dreg: str = "%vd", a: str = "%v0", b: str = "%v1", c: str = "%v2") -> str:
    return f"fma.{rnd}.bf16 {dreg}, {a}, {b}, {c};"


def _x2_fma(rnd: str, dreg: str = "%wd", a: str = "%w0", b: str = "%w1", c: str = "%w2") -> str:
    return f"fma.{rnd}.bf16x2 {dreg}, {a}, {b}, {c};"


def _scalar_case(rnd: str, context: str = "baseline") -> Case:
    coords = {"dtype": "bf16", "rounding": rnd, "context": context}
    return Case("", coords, parameters=PARAMS, registers=SCALAR_REGS, preparation=SCALAR_PREP, target=(_scalar_fma(rnd),), observation=SCALAR_OBS)


def _x2_case(rnd: str, context: str = "baseline") -> Case:
    coords = {"dtype": "bf16x2", "rounding": rnd, "context": context}
    return Case("", coords, parameters=PARAMS, registers=X2_REGS, preparation=X2_PREP, target=(_x2_fma(rnd),), observation=X2_OBS)


def fma_cases() -> list[Case]:
    cases = []
    for rnd in ROUNDINGS:
        cases.append(_scalar_case(rnd))
        cases.append(_x2_case(rnd))
    return cases


def fma_expanded() -> list[Case]:
    cases = fma_cases()

    # CTX.lane_asymmetric_pack: bf16x2 operands built from genuinely distinct
    # per-lane producers via the `{lo, hi}` pack syntax (not a broadcast
    # constant) -- covers the "packed lane 非对称" completion-gate item.
    for rnd in ("rn", "rz"):
        regs = (
            ".reg .b16 %pa0, %pa1, %pb0, %pb1, %pc0, %pc1;",
            ".reg .b32 %w0, %w1, %w2, %wd;",
            ".reg .u64 %out;",
        )
        prep = (
            "ld.param.u64 %out, [p_out];",
            "mov.u16 %pa0, 0x3F80;", "mov.u16 %pa1, 0x4000;",
            "mov.u16 %pb0, 0xBF80;", "mov.u16 %pb1, 0x3F00;",
            "mov.u16 %pc0, 0x3F80;", "mov.u16 %pc1, 0xC000;",
            "mov.b32 %w0, {%pa0, %pa1};", "mov.b32 %w1, {%pb0, %pb1};", "mov.b32 %w2, {%pc0, %pc1};",
        )
        coords = {"dtype": "bf16x2", "rounding": rnd, "context": "lane_asymmetric_pack"}
        cases.append(Case("", coords, parameters=PARAMS, registers=regs, preparation=prep, target=(_x2_fma(rnd),), observation=X2_OBS))

    # CTX.f32_cvt_consumer: fma result consumed by cvt.f32.bf16 (scalar only
    # -- there is no unpack instruction for bf16x2 in this ISA/toolchain,
    # confirmed by a failed `mov.b16 {%rh0,%rh1}, %r32;` probe).
    for rnd in ("rn", "rz"):
        regs = SCALAR_REGS + (".reg .f32 %fo;",)
        coords = {"dtype": "bf16", "rounding": rnd, "context": "f32_cvt_consumer"}
        cases.append(Case("", coords, parameters=PARAMS, registers=regs, preparation=SCALAR_PREP, target=(_scalar_fma(rnd),), observation=("cvt.f32.bf16 %fo, %vd;", "st.global.f32 [%out], %fo;")))

    # CTX.chain: two dependent fma instructions (second consumes the first's
    # destination as its `a` operand) -- "双 fma 链".
    for rnd in ("rn", "rz"):
        coords = {"dtype": "bf16", "rounding": rnd, "context": "chain"}
        cases.append(Case("", coords, parameters=PARAMS, registers=SCALAR_REGS, preparation=SCALAR_PREP, target=(_scalar_fma(rnd), _scalar_fma(rnd, a="%vd")), observation=SCALAR_OBS))
    coords = {"dtype": "bf16x2", "rounding": "rn", "context": "chain"}
    cases.append(Case("", coords, parameters=PARAMS, registers=X2_REGS, preparation=X2_PREP, target=(_x2_fma("rn"), _x2_fma("rn", a="%wd")), observation=X2_OBS))

    # CTX.guarded: predicated issue (uniform predicate derived from %tid.x,
    # never named %tid itself).
    for rnd, regs0, prep0, fma_fn, dreg, obs in (
        ("rn", SCALAR_REGS, SCALAR_PREP, _scalar_fma, "%vd", SCALAR_OBS),
        ("rn", X2_REGS, X2_PREP, _x2_fma, "%wd", X2_OBS),
    ):
        dtype = "bf16" if fma_fn is _scalar_fma else "bf16x2"
        extra_regs = (".reg .u32 %t0;", ".reg .pred %pg;")
        extra_prep = ("mov.u32 %t0, %tid.x;", "setp.lt.u32 %pg, %t0, 16;", f"mov.{'u16' if dtype == 'bf16' else 'b32'} {dreg}, 0;")
        coords = {"dtype": dtype, "rounding": rnd, "context": "guarded"}
        cases.append(Case("", coords, parameters=PARAMS, registers=regs0 + extra_regs, preparation=prep0 + extra_prep, target=("@%pg " + fma_fn(rnd),), observation=obs))

    # CTX.template_wide: padded parameter signature (P1-1 template axis).
    wide_params = (".param .u32 p_pad0", ".param .u64 p_out", ".param .u64 p_pad1", ".param .u32 p_pad2")
    coords = {"dtype": "bf16", "rounding": "rn", "context": "template_wide"}
    cases.append(Case("", coords, parameters=wide_params, registers=SCALAR_REGS, preparation=SCALAR_PREP, target=(_scalar_fma("rn"),), observation=SCALAR_OBS))
    coords = {"dtype": "bf16x2", "rounding": "rn", "context": "template_wide"}
    cases.append(Case("", coords, parameters=wide_params, registers=X2_REGS, preparation=X2_PREP, target=(_x2_fma("rn"),), observation=X2_OBS))

    # CTX.producer_indirect: operands loaded from global memory, not movs
    # (P1-2 rematerialization axis -- non-foldable source).
    scalar_indirect_regs = SCALAR_REGS + (".reg .u64 %in;",)
    scalar_indirect_prep = ("ld.param.u64 %out, [p_out];", "ld.param.u64 %in, [p_in];", "ld.global.b16 %v0, [%in];", "ld.global.b16 %v1, [%in+2];", "ld.global.b16 %v2, [%in+4];")
    coords = {"dtype": "bf16", "rounding": "rn", "context": "producer_indirect"}
    cases.append(Case("", coords, parameters=PARAMS_IN, registers=scalar_indirect_regs, preparation=scalar_indirect_prep, target=(_scalar_fma("rn"),), observation=SCALAR_OBS))
    x2_indirect_regs = X2_REGS + (".reg .u64 %in;",)
    x2_indirect_prep = ("ld.param.u64 %out, [p_out];", "ld.param.u64 %in, [p_in];", "ld.global.b32 %w0, [%in];", "ld.global.b32 %w1, [%in+4];", "ld.global.b32 %w2, [%in+8];")
    coords = {"dtype": "bf16x2", "rounding": "rn", "context": "producer_indirect"}
    cases.append(Case("", coords, parameters=PARAMS_IN, registers=x2_indirect_regs, preparation=x2_indirect_prep, target=(_x2_fma("rn"),), observation=X2_OBS))

    # CTX.consumption_distance: filler ops between fma and its consumer
    # (P0-1 analog for an ALU family -- control-word/scheduling context).
    filler_u32 = tuple("add.u32 %fill, %fill, 1;" for _ in range(8))
    coords = {"dtype": "bf16", "rounding": "rn", "context": "consumption_distance_8"}
    cases.append(Case("", coords, parameters=PARAMS, registers=SCALAR_REGS + (".reg .u32 %fill;",), preparation=SCALAR_PREP + ("mov.u32 %fill, 0;",), target=(_scalar_fma("rn"),), observation=filler_u32 + SCALAR_OBS))
    coords = {"dtype": "bf16x2", "rounding": "rn", "context": "consumption_distance_8"}
    cases.append(Case("", coords, parameters=PARAMS, registers=X2_REGS + (".reg .u32 %fill;",), preparation=X2_PREP + ("mov.u32 %fill, 0;",), target=(_x2_fma("rn"),), observation=filler_u32 + X2_OBS))

    # CTX.parallel_depth: four independent fma's in flight before a joint
    # consumer (P0-1 analog for in-flight depth on an ALU family).
    scalar_depth_regs = (".reg .b16 %v0, %v1, %v2, %vd0, %vd1, %vd2, %vd3;", ".reg .u64 %out;")
    scalar_depth_target = tuple(_scalar_fma("rn", dreg=f"%vd{i}") for i in range(4))
    scalar_depth_obs = ("xor.b16 %vd0, %vd0, %vd1;", "xor.b16 %vd0, %vd0, %vd2;", "xor.b16 %vd0, %vd0, %vd3;", "st.global.b16 [%out], %vd0;")
    coords = {"dtype": "bf16", "rounding": "rn", "context": "parallel_depth_4"}
    cases.append(Case("", coords, parameters=PARAMS, registers=scalar_depth_regs, preparation=SCALAR_PREP, target=scalar_depth_target, observation=scalar_depth_obs))

    x2_depth_regs = (".reg .b32 %w0, %w1, %w2, %wd0, %wd1, %wd2, %wd3;", ".reg .u64 %out;")
    x2_depth_target = tuple(_x2_fma("rn", dreg=f"%wd{i}") for i in range(4))
    x2_depth_obs = ("xor.b32 %wd0, %wd0, %wd1;", "xor.b32 %wd0, %wd0, %wd2;", "xor.b32 %wd0, %wd0, %wd3;", "st.global.b32 [%out], %wd0;")
    coords = {"dtype": "bf16x2", "rounding": "rn", "context": "parallel_depth_4"}
    cases.append(Case("", coords, parameters=PARAMS, registers=x2_depth_regs, preparation=X2_PREP, target=x2_depth_target, observation=x2_depth_obs))

    return cases


MIXED_REGS = (".reg .b16 %v0, %v1, %v2, %vd;", ".reg .b32 %w0, %w1, %w2, %wd;", ".reg .u64 %out;")
MIXED_PREP = ("ld.param.u64 %out, [p_out];", "mov.u16 %v0, 0x3F80;", "mov.u16 %v1, 0x4000;", "mov.u16 %v2, 0xBF80;", "mov.b32 %w0, 0x40003F80;", "mov.b32 %w1, 0xBF803F80;", "mov.b32 %w2, 0x3F803F80;")


def fma_negative() -> list[Case]:
    def probe(coords: dict, target: str, reason: str, diagnostic: str) -> Case:
        return Case("", coords, parameters=PARAMS, registers=SCALAR_REGS, preparation=SCALAR_PREP, target=(target,), observation=(), expected="reject", reason=reason, expected_diagnostic=diagnostic)

    def probe_mixed(coords: dict, target: str, reason: str, diagnostic: str) -> Case:
        return Case("", coords, parameters=PARAMS, registers=MIXED_REGS, preparation=MIXED_PREP, target=(target,), observation=(), expected="reject", reason=reason, expected_diagnostic=diagnostic)

    f16_mix_regs = SCALAR_REGS + (".reg .f16 %fh0;",)
    f16_mix_case = Case(
        "", {"probe": "f16_operand_mismatch"}, parameters=PARAMS, registers=f16_mix_regs, preparation=SCALAR_PREP,
        target=("fma.rn.bf16 %vd, %fh0, %v1, %v2;",), observation=(), expected="reject",
        reason="a .f16-typed register cannot fill a bf16 operand slot -- bf16 and f16 do not share a register class",
        expected_diagnostic="Arguments mismatch for instruction 'fma'",
    )

    return [
        probe({"probe": "rounding_required"}, "fma.bf16 %vd, %v0, %v1, %v2;", "fma requires an explicit rounding token, unlike add/sub/mul", "Rounding modifier required for instruction 'fma'"),
        probe({"probe": "ftz_illegal"}, "fma.rn.ftz.bf16 %vd, %v0, %v1, %v2;", ".ftz is illegal for bf16 fma on every rounding path", "Illegal modifier '.ftz' for instruction 'fma'"),
        probe({"probe": "sat_illegal"}, "fma.rn.sat.bf16 %vd, %v0, %v1, %v2;", ".sat is illegal for bf16 fma on every rounding path", "Illegal modifier '.sat' for instruction 'fma'"),
        f16_mix_case,
        probe_mixed({"probe": "scalar_packed_operand_mismatch"}, "fma.rn.bf16 %vd, %w0, %v1, %v2;", "a .b32 register cannot fill a bf16 scalar operand slot", "Arguments mismatch for instruction 'fma'"),
        probe_mixed({"probe": "x2_scalar_operand_mismatch"}, "fma.rn.bf16x2 %wd, %v0, %w1, %w2;", "a .b16 register cannot fill a bf16x2 packed operand slot", "Arguments mismatch for instruction 'fma'"),
        probe({"probe": "operand_negate_a"}, "fma.rn.bf16 %vd, -%v0, %v1, %v2;", "operand negation is not a legal PTX-syntax route to fold neg into fma for this type family", "Operand negation not allowed for instruction 'fma'"),
        probe({"probe": "operand_abs_b"}, "fma.rn.bf16 %vd, %v0, |%v1|, %v2;", "operand abs-bars are not accepted for fma.bf16 (unlike min/max)", "Parsing error near '|'"),
        probe({"probe": "multiple_rounding_tokens"}, "fma.rn.rz.bf16 %vd, %v0, %v1, %v2;", "at most one rounding token is accepted", "Multiple rounding modifiers specified"),
        # complement sampling outside the assumed-legal surface (P0-2)
        probe({"probe": "immediate_c_operand"}, "fma.rn.bf16 %vd, %v0, %v1, 0x3F80;", "complement sample: immediate literal directly as fma's c operand", "Arguments mismatch for instruction 'fma'"),
        probe({"probe": "sat_illegal_on_emulated_rz_path"}, "fma.rz.sat.bf16 %vd, %v0, %v1, %v2;", "complement sample: .sat stays illegal even on the F32-emulated .rz path (checked before path selection)", "Illegal modifier '.sat' for instruction 'fma'"),
    ]


FACTORS = (
    {"id": "SF.dtype", "levels": ["bf16", "bf16x2"]},
    {"id": "SF.rounding", "levels": ["rn", "rz", "rm", "rp"]},
    {"id": "CTX.context", "levels": ["baseline", "lane_asymmetric_pack", "f32_cvt_consumer", "chain", "guarded", "template_wide", "producer_indirect", "consumption_distance_8", "parallel_depth_4"]},
)

SPEC = Spec(
    family="bf16",
    opcode="fma",
    ptx_opcode="fma",
    target_patterns=("HFMA2.BF16_V2", "FFMA.RZ", "FFMA.RM", "FFMA.RP"),
    factors=FACTORS,
    syntax_cases=fma_cases,
    expanded_cases=fma_expanded,
    negative_cases=fma_negative,
    empty_target_allowed=lambda _coordinates: False,
)

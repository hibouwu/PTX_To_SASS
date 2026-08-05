#!/usr/bin/env python3
"""Independent experiment definition for tanh on Thor.

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 (`sm_110a`): `tanh.approx.f32` -> `MUFU.TANH`,
`tanh.approx.f16`/`.bf16` -> `MUFU.TANH.F16`/`MUFU.TANH.BF16` (direct, one
PTX instruction to one SASS instruction), `tanh.approx.f16x2`/`.bf16x2` ->
a lane-split sequence (`PRMT` unpack at O0, none needed at O3 since the
second `MUFU.TANH.*` reads the `.H1` half directly) of two
`MUFU.TANH.F16`/`MUFU.TANH.BF16` plus a `PRMT` repack. `.approx` is
mandatory on every legal form; `.rn`, `.ftz` and `.sat` are illegal on
`tanh` for every dtype (no exceptions found). `tanh` has no `.f64` or
integer form. A guard predicate does not attach to `MUFU.TANH` itself:
ptxas computes it unconditionally and selects the result with `FSEL`.
`target_patterns = ("MUFU.TANH",)` is a substring match that covers all
three dtype-suffixed mnemonics by construction.
"""

from suite_runtime import Case, Spec

DTYPES = {
    "f32":    {"reg": ".f32", "ld": "ld.global.f32", "st": "st.global.f32", "suffix": "f32", "packed": False},
    "f16":    {"reg": ".b16", "ld": "ld.global.b16", "st": "st.global.b16", "suffix": "f16", "packed": False},
    "bf16":   {"reg": ".b16", "ld": "ld.global.b16", "st": "st.global.b16", "suffix": "bf16", "packed": False},
    "f16x2":  {"reg": ".b32", "ld": "ld.global.b32", "st": "st.global.b32", "suffix": "f16x2", "packed": True, "lane": "f16"},
    "bf16x2": {"reg": ".b32", "ld": "ld.global.b32", "st": "st.global.b32", "suffix": "bf16x2", "packed": True, "lane": "bf16"},
}
CONSUMERS = ("direct", "mul", "cvt")

PARAMS_1IN = (".param .u64 p_in", ".param .u64 p_out")
PARAMS_2IN = (".param .u64 p_in", ".param .u64 p_in2", ".param .u64 p_out")


def _case(dtype: str, consumer: str, context: str = "baseline") -> Case:
    info = DTYPES[dtype]
    reg_ty, ld, st, suffix, packed = info["reg"], info["ld"], info["st"], info["suffix"], info["packed"]
    coords = {"dtype": dtype, "consumer": consumer, "context": context}
    tanh_line = f"tanh.approx.{suffix} %d, %a;"

    if consumer == "direct":
        parameters = PARAMS_1IN
        registers = (".reg .b64 %rin, %rout;", f".reg {reg_ty} %a, %d;")
        preparation = ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", f"{ld} %a, [%rin];")
        observation = (f"{st} [%rout], %d;",)
    elif consumer == "mul":
        parameters = PARAMS_2IN
        registers = (".reg .b64 %rin, %rin2, %rout;", f".reg {reg_ty} %a, %b, %d, %e;")
        preparation = (
            "ld.param.b64 %rin, [p_in];",
            "ld.param.b64 %rin2, [p_in2];",
            "ld.param.b64 %rout, [p_out];",
            f"{ld} %a, [%rin];",
            f"{ld} %b, [%rin2];",
        )
        observation = (f"mul.{suffix} %e, %d, %b;", f"{st} [%rout], %e;")
    else:  # cvt: post-activation convert epilogue
        parameters = PARAMS_1IN
        if not packed:
            if dtype == "f32":
                registers = (".reg .b64 %rin, %rout;", ".reg .f32 %a, %d;", ".reg .b16 %h;")
                preparation = ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", f"{ld} %a, [%rin];")
                observation = ("cvt.rn.f16.f32 %h, %d;", "st.global.b16 [%rout], %h;")
            else:
                registers = (".reg .b64 %rin, %rout;", f".reg {reg_ty} %a, %d;", ".reg .f32 %f;")
                preparation = ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", f"{ld} %a, [%rin];")
                observation = (f"cvt.f32.{suffix} %f, %d;", "st.global.f32 [%rout], %f;")
        else:
            lane = info["lane"]
            registers = (
                ".reg .b64 %rin, %rout;",
                f".reg {reg_ty} %a, %d;",
                ".reg .b16 %dlo, %dhi;",
                ".reg .f32 %flo, %fhi, %fsum;",
            )
            preparation = ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", f"{ld} %a, [%rin];")
            observation = (
                "mov.b32 {%dlo, %dhi}, %d;",
                f"cvt.f32.{lane} %flo, %dlo;",
                f"cvt.f32.{lane} %fhi, %dhi;",
                "add.f32 %fsum, %flo, %fhi;",
                "st.global.f32 [%rout], %fsum;",
            )

    return Case("", coords, parameters=parameters, registers=registers, preparation=preparation, target=(tanh_line,), observation=observation)


def base_cases() -> list[Case]:
    # SF.dtype x SF.consumer full factorial (5 legal dtypes x 3 consumer patterns)
    return [_case(dtype, consumer) for dtype in DTYPES for consumer in CONSUMERS]


def _ctx_producer_indirect() -> Case:
    # P1-2: source operand is not a plain load, it is computed from a
    # non-foldable special register plus a memory-loaded bias.
    coords = {"dtype": "f32", "consumer": "direct", "context": "producer_indirect"}
    registers = (".reg .b64 %rin, %rout;", ".reg .f32 %a, %bias, %d;", ".reg .b32 %t0;")
    preparation = (
        "ld.param.b64 %rin, [p_in];",
        "ld.param.b64 %rout, [p_out];",
        "ld.global.f32 %bias, [%rin];",
        "mov.u32 %t0, %tid.x;",
        "cvt.rn.f32.u32 %a, %t0;",
        "add.f32 %a, %a, %bias;",
    )
    return Case("", coords, parameters=PARAMS_1IN, registers=registers, preparation=preparation, target=("tanh.approx.f32 %d, %a;",), observation=("st.global.f32 [%rout], %d;",))


def _ctx_cvt_producer_f16() -> Case:
    # requested axis: f32 -> cvt -> tanh.f16 vs. baseline direct f16 load -> tanh.f16
    coords = {"dtype": "f16", "consumer": "direct", "context": "cvt_producer"}
    registers = (".reg .b64 %rin, %rout;", ".reg .f32 %a;", ".reg .b16 %h, %d;")
    preparation = ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", "ld.global.f32 %a, [%rin];", "cvt.rn.f16.f32 %h, %a;")
    return Case("", coords, parameters=PARAMS_1IN, registers=registers, preparation=preparation, target=("tanh.approx.f16 %d, %h;",), observation=("st.global.b16 [%rout], %d;",))


def _ctx_double_chain() -> Case:
    coords = {"dtype": "f32", "consumer": "direct", "context": "double_chain"}
    registers = (".reg .b64 %rin, %rout;", ".reg .f32 %a, %d, %e;")
    preparation = ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", "ld.global.f32 %a, [%rin];")
    return Case("", coords, parameters=PARAMS_1IN, registers=registers, preparation=preparation, target=("tanh.approx.f32 %d, %a;", "tanh.approx.f32 %e, %d;"), observation=("st.global.f32 [%rout], %e;",))


def _ctx_lane_asym(dtype: str) -> Case:
    # x2 form built from two independently loaded lanes (not one packed load).
    # Both lanes must be consumed or O3 DCEs the whole computation back to a
    # single scalar MUFU.TANH.* (calibrated: probe:tanh_f16x2_asym_pack).
    info = DTYPES[dtype]
    suffix, lane = info["suffix"], info["lane"]
    coords = {"dtype": dtype, "consumer": "cvt", "context": "lane_asym"}
    parameters = PARAMS_2IN
    registers = (
        ".reg .b64 %rin, %rin2, %rout;",
        ".reg .b16 %lo, %hi;",
        ".reg .b32 %a, %d;",
        ".reg .b16 %dlo, %dhi;",
        ".reg .f32 %flo, %fhi, %fsum;",
    )
    preparation = (
        "ld.param.b64 %rin, [p_in];",
        "ld.param.b64 %rin2, [p_in2];",
        "ld.param.b64 %rout, [p_out];",
        "ld.global.b16 %lo, [%rin];",
        "ld.global.b16 %hi, [%rin2];",
        "mov.b32 %a, {%lo, %hi};",
    )
    observation = (
        "mov.b32 {%dlo, %dhi}, %d;",
        f"cvt.f32.{lane} %flo, %dlo;",
        f"cvt.f32.{lane} %fhi, %dhi;",
        "add.f32 %fsum, %flo, %fhi;",
        "st.global.f32 [%rout], %fsum;",
    )
    return Case("", coords, parameters=parameters, registers=registers, preparation=preparation, target=(f"tanh.approx.{suffix} %d, %a;",), observation=observation)


def _ctx_guard() -> Case:
    # calibrated: the predicate does NOT attach to MUFU.TANH; ptxas computes
    # it unconditionally and FSELs between it and the else-branch value.
    coords = {"dtype": "f32", "consumer": "direct", "context": "guard"}
    registers = (".reg .b64 %rin, %rout;", ".reg .f32 %a, %d;", ".reg .b32 %t0;", ".reg .pred %p;")
    preparation = (
        "ld.param.b64 %rin, [p_in];",
        "ld.param.b64 %rout, [p_out];",
        "ld.global.f32 %a, [%rin];",
        "mov.u32 %t0, %tid.x;",
        "setp.lt.u32 %p, %t0, 16;",
    )
    target = ("@%p tanh.approx.f32 %d, %a;", "@!%p mov.f32 %d, 0f00000000;")
    return Case("", coords, parameters=PARAMS_1IN, registers=registers, preparation=preparation, target=target, observation=("st.global.f32 [%rout], %d;",))


def _ctx_template_wide() -> Case:
    coords = {"dtype": "f32", "consumer": "direct", "context": "template_wide"}
    parameters = (".param .u32 p_pad0", ".param .u64 p_in", ".param .u64 p_pad1", ".param .u64 p_out", ".param .u32 p_pad2")
    registers = (".reg .b64 %rin, %rout;", ".reg .f32 %a, %d;")
    preparation = ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", "ld.global.f32 %a, [%rin];")
    return Case("", coords, parameters=parameters, registers=registers, preparation=preparation, target=("tanh.approx.f32 %d, %a;",), observation=("st.global.f32 [%rout], %d;",))


def _ctx_inflight(depth: int) -> Case:
    # P0-1: control-word axis. Calibrated (probe:tanh_f32_inflight_2_*): the
    # word-1 stall/barrier bits around MUFU.TANH change with in-flight
    # depth and consumer distance even though there is no visible scoreboard
    # instruction -- MUFU is a fixed-latency functional unit, not an async
    # engine, but its completion tracking is still a control-word resource.
    coords = {"dtype": "f32", "consumer": "direct", "context": f"inflight_depth_{depth}"}
    a_regs = ", ".join(f"%a{i}" for i in range(depth))
    d_regs = ", ".join(f"%d{i}" for i in range(depth))
    registers = (".reg .b64 %rin, %rout;", f".reg .f32 {a_regs}, {d_regs}, %s;")
    preparation = ["ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];"]
    preparation += [f"ld.global.f32 %a{i}, [%rin+{4 * i}];" for i in range(depth)]
    target = tuple(f"tanh.approx.f32 %d{i}, %a{i};" for i in range(depth))
    reduce_ops = ["add.f32 %s, %d0, %d1;"] if depth == 2 else [
        "add.f32 %s, %d0, %d1;",
        "add.f32 %s, %s, %d2;",
        "add.f32 %s, %s, %d3;",
    ]
    observation = tuple(reduce_ops + ["st.global.f32 [%rout], %s;"])
    return Case("", coords, parameters=PARAMS_1IN, registers=registers, preparation=tuple(preparation), target=target, observation=observation)


def _ctx_immediate_source() -> Case:
    # discovery (P0-2 complement channel): MUFU.TANH accepts an immediate
    # source operand directly; PTX allows a literal constant in place of a
    # register for tanh.approx.f32.
    coords = {"dtype": "f32", "consumer": "direct", "context": "immediate_source"}
    registers = (".reg .b64 %rout;", ".reg .f32 %d;")
    preparation = ("ld.param.b64 %rout, [p_out];",)
    return Case("", coords, parameters=PARAMS_1IN, registers=registers, preparation=preparation, target=("tanh.approx.f32 %d, 0f3f800000;",), observation=("st.global.f32 [%rout], %d;",))


def tanh_expanded() -> list[Case]:
    cases = base_cases()
    cases.append(_ctx_producer_indirect())
    cases.append(_ctx_cvt_producer_f16())
    cases.append(_ctx_double_chain())
    cases.append(_ctx_lane_asym("f16x2"))
    cases.append(_ctx_lane_asym("bf16x2"))
    cases.append(_ctx_guard())
    cases.append(_ctx_template_wide())
    cases.append(_ctx_inflight(2))
    cases.append(_ctx_inflight(4))
    cases.append(_ctx_immediate_source())
    return cases


def tanh_negative() -> list[Case]:
    def probe(coords: dict, dtype_setup: tuple, target: str, reason: str, diagnostic: str) -> Case:
        registers, preparation = dtype_setup
        return Case("", coords, parameters=PARAMS_1IN, registers=registers, preparation=preparation, target=(target,), observation=(), expected="reject", reason=reason, expected_diagnostic=diagnostic)

    f32_setup = ((".reg .b64 %rin, %rout;", ".reg .f32 %a, %d;"), ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", "ld.global.f32 %a, [%rin];"))
    f16_setup = ((".reg .b64 %rin, %rout;", ".reg .b16 %a, %d;"), ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", "ld.global.b16 %a, [%rin];"))
    f64_setup = ((".reg .b64 %rin, %rout;", ".reg .f64 %a, %d;"), ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", "ld.global.f64 %a, [%rin];"))
    s32_setup = ((".reg .b64 %rin, %rout;", ".reg .s32 %a, %d;"), ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", "ld.global.s32 %a, [%rin];"))
    dst_mismatch_setup = ((".reg .b64 %rin, %rout;", ".reg .b16 %a;", ".reg .b32 %d;"), ("ld.param.b64 %rin, [p_in];", "ld.param.b64 %rout, [p_out];", "ld.global.b16 %a, [%rin];"))

    return [
        probe({"probe": "missing_approx"}, f32_setup, "tanh.f32 %d, %a;", ".approx is mandatory on tanh, not optional", ".approx modifier required for instruction 'tanh'"),
        probe({"probe": "f64_unsupported"}, f64_setup, "tanh.approx.f64 %d, %a;", "tanh has no .f64 form", "Unexpected instruction types specified for 'tanh'"),
        probe({"probe": "integer_dtype"}, s32_setup, "tanh.approx.s32 %d, %a;", "tanh has no integer form", "Unexpected instruction types specified for 'tanh'"),
        probe({"probe": "rn_rounding"}, f32_setup, "tanh.approx.rn.f32 %d, %a;", "tanh has no rounding modifier (only .approx)", "Illegal rounding modifier for instruction 'tanh'"),
        probe({"probe": "ftz_f32"}, f32_setup, "tanh.approx.ftz.f32 %d, %a;", "tanh has no .ftz form on f32", "Illegal modifier '.ftz' for instruction 'tanh'"),
        probe({"probe": "ftz_f16"}, f16_setup, "tanh.approx.ftz.f16 %d, %a;", "tanh has no .ftz form on f16 either (uniform across dtypes)", "Illegal modifier '.ftz' for instruction 'tanh'"),
        probe({"probe": "sat_f32"}, f32_setup, "tanh.approx.sat.f32 %d, %a;", "tanh has no .sat modifier", "Illegal modifier '.sat' for instruction 'tanh'"),
        probe({"probe": "dst_width_mismatch"}, dst_mismatch_setup, "tanh.approx.f16 %d, %a;", "dst register width must match the f16 result width", "Arguments mismatch for instruction 'tanh'"),
        # complement sampling outside the primary modifier/dtype axes (P0-2)
        probe({"probe": "f16x2_scalar_args_complement"}, f16_setup, "tanh.approx.f16x2 %d, %a;", "complement: f16x2 opcode fed scalar .b16 operands (width/arity)", "Arguments mismatch for instruction 'tanh'"),
        probe({"probe": "extra_operand_complement"}, f32_setup, "tanh.approx.f32 %d, %a, %a;", "complement: tanh takes exactly one source operand", "Arguments mismatch for instruction 'tanh'"),
    ]


FACTORS = (
    {"id": "SF.dtype", "levels": ["f32", "f16", "f16x2", "bf16", "bf16x2"]},
    {"id": "SF.consumer", "levels": ["direct", "mul", "cvt"]},
    {"id": "CTX.context", "levels": ["baseline", "producer_indirect", "cvt_producer", "double_chain", "lane_asym", "guard", "template_wide", "inflight_depth_2", "inflight_depth_4", "immediate_source"]},
)

SPEC = Spec(
    family="act",
    opcode="tanh",
    ptx_opcode="tanh.approx",
    target_patterns=("MUFU.TANH",),
    factors=FACTORS,
    syntax_cases=base_cases,
    expanded_cases=tanh_expanded,
    negative_cases=tanh_negative,
    empty_target_allowed=lambda _coordinates: False,
)

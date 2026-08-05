#!/usr/bin/env python3
"""Independent experiment definition for `membar` on Thor.

Calibrated against ptxas V13.0.88 / nvdisasm V13.0.85 (`sm_110a`, PTX 9.0,
isolated single-membar kernels, O0 and O3): `membar.{level}` accepts exactly
three legacy levels -- `cta`, `gl`, `sys` (NOT `gpu`; that spelling is
illegal on `membar`, only the newer `fence` instruction uses `gpu`).  Each
level is byte-identical to the corresponding `fence.sc.<scope>` form from
the `fence/thor_ptx90` suite: `membar.cta` == `fence.sc.cta`
(`MEMBAR.SC.CTA`), `membar.gl` == `fence.sc.gpu` == `fence.sc.cluster`
(`MEMBAR.SC.GPU`+`ERRBAR`+`CGAERRBAR`+`CCTL.IVALL`), `membar.sys` ==
`fence.sc.sys` (`MEMBAR.SC.SYS`+`ERRBAR`+`CGAERRBAR`+`CCTL.IVALL`).  membar
is a strict subset of fence's `sc` row (it has no cluster-scope spelling and
no acquire/release/acq_rel sem); this suite exists to pin that subset
relationship with its own independent evidence rather than merely asserting
it in prose.
"""

from suite_runtime import Case, Spec

LEVEL_TOKENS = ("cta", "gl", "sys")

PARAMS = (".param .u64 p_out",)
REGISTERS = (".reg .b64 %out;", ".reg .u32 %v;")
PREPARATION = ("ld.param.b64 %out, [p_out];", "mov.u32 %v, %tid.x;")
OBSERVATION = ("st.global.u32 [%out], %v;",)
DIRECTIVES = (".reqntid 128",)


def _membar(level: str, guard: str = "") -> str:
    return f"{guard}membar.{level};"


def _case(level: str, context: str = "baseline", target: tuple[str, ...] | None = None, extra_prep: tuple[str, ...] = (), extra_regs: tuple[str, ...] = (), parameters: tuple[str, ...] = PARAMS) -> Case:
    coords = {"level": level, "context": context}
    return Case(
        "",
        coords,
        parameters=parameters,
        registers=REGISTERS + extra_regs,
        preparation=PREPARATION + extra_prep,
        target=target if target is not None else (_membar(level),),
        observation=OBSERVATION,
        directives=DIRECTIVES,
    )


def membar_cases() -> list[Case]:
    return [_case(level) for level in LEVEL_TOKENS]


def membar_expanded() -> list[Case]:
    cases = membar_cases()

    # CTX.pre_post_global: realistic release-then-acquire flag pattern
    cases.append(_case(
        "gl", context="pre_ld_global_post_st_global",
        extra_regs=(".reg .u32 %pre; .reg .b64 %in;",),
        extra_prep=("ld.param.b64 %in, [p_in];", "ld.global.u32 %pre, [%in];", "add.u32 %v, %v, %pre;"),
        parameters=PARAMS + (".param .u64 p_in",),
    ))

    # CTX.pre_post_shared: cta-level membar between shared st/ld
    cases.append(_case(
        "cta", context="pre_st_shared_post_ld_shared",
        extra_regs=(".shared .align 4 .b32 slot;",),
        extra_prep=("st.shared.u32 [slot], %v;",),
    ))

    # CTX.double_same_level: adjacent identical membars -- no merge/dedup expected (cross-checked against fence)
    cases.append(_case("gl", context="double_same_level", target=(_membar("gl"), _membar("gl"))))

    # CTX.double_diff_level: adjacent membars at different levels
    cases.append(_case("cta", context="double_diff_level", target=(_membar("cta"), _membar("gl"))))

    # CTX.guard: predicated issue
    cases.append(_case(
        "gl", context="guarded",
        extra_regs=(".reg .pred %p;",),
        extra_prep=("setp.lt.u32 %p, %v, 16;",),
        target=(_membar("gl", guard="@%p "),),
    ))

    # CTX.inflight_depth: P0-1 control-word axis
    for depth in (2, 4):
        loads = tuple(f"ld.global.u32 %d{i}, [%in+{i * 4}];" for i in range(depth))
        merges = tuple(f"add.u32 %v, %v, %d{i};" for i in range(depth))
        regs = tuple(f".reg .u32 %d{i};" for i in range(depth))
        cases.append(_case(
            "gl", context=f"inflight_depth_{depth}",
            extra_regs=(".reg .b64 %in;",) + regs,
            extra_prep=("ld.param.b64 %in, [p_in];",) + loads + merges,
            parameters=PARAMS + (".param .u64 p_in",),
        ))

    # CTX.kernel_template: padded signature (P1-1 axis)
    wide_params = (".param .u32 p_pad0", ".param .u64 p_out", ".param .u64 p_pad1", ".param .u32 p_pad2")
    cases.append(_case("sys", context="template_wide", parameters=wide_params))

    return cases


def membar_negative() -> list[Case]:
    def probe(coords: dict, target: str, reason: str, diagnostic: str) -> Case:
        return Case("", coords, parameters=(), registers=(), preparation=(), target=(target,), observation=(), directives=(), expected="reject", reason=reason, expected_diagnostic=diagnostic)

    return [
        probe({"probe": "unknown_level_token"}, "membar.warp;", "warp is not a defined membar level", "Unknown modifier '.warp'"),
        probe({"probe": "missing_level"}, "membar;", "level modifier is mandatory", "Membar level required for instruction 'membar'"),
        probe({"probe": "unexpected_operand"}, "membar.cta %r0;", "membar takes no operands", "Arguments mismatch for instruction 'membar'"),
        probe({"probe": "illegal_level_cluster"}, "membar.cluster;", "cluster is a fence-only scope, not a membar level", "Illegal modifier '.cluster' for instruction 'membar'"),
        # complement sampling outside the assumed-legal surface (P0-2): does membar accept the newer fence vocabulary?
        probe({"probe": "illegal_level_gpu"}, "membar.gpu;", "gpu is the fence spelling of gl; membar keeps the legacy token only", "Illegal modifier '.gpu' for instruction 'membar'"),
        probe({"probe": "illegal_sem_sc"}, "membar.sc.cta;", "membar has no sem axis (no sc/acq_rel/acquire/release tokens)", "Illegal modifier '.sc' for instruction 'membar'"),
    ]


FACTORS = (
    {"id": "SF.level", "levels": ["cta", "gl", "sys"]},
    {"id": "CTX.context", "levels": ["baseline", "pre_ld_global_post_st_global", "pre_st_shared_post_ld_shared", "double_same_level", "double_diff_level", "guarded", "inflight_depth_2", "inflight_depth_4", "template_wide"]},
)

SPEC = Spec(
    family="fence",
    opcode="membar",
    ptx_opcode="membar",
    target_patterns=("MEMBAR", "ERRBAR", "CCTL.IVALL"),
    factors=FACTORS,
    syntax_cases=membar_cases,
    expanded_cases=membar_expanded,
    negative_cases=membar_negative,
    empty_target_allowed=lambda _coordinates: False,
)

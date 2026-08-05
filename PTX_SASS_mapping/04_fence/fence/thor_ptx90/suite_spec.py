#!/usr/bin/env python3
"""Independent experiment definition for `fence` on Thor.

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 (`sm_110a`, PTX 9.0, isolated single-fence kernels,
O0 and O3): `fence.{sem}.{scope}` accepts FOUR sem tokens (`sc`,
`acq_rel`, `acquire`, `release` -- the PTX ISA prose only advertises the
combination is legal, but ptxas quietly accepts `acquire`/`release` on
their own too) crossed with FOUR scope tokens (`cta`, `cluster`, `gpu`,
`sys`); all 16 combinations compile. The scope axis collapses in SASS:
`cluster` and `gpu` are byte-identical for every sem (a runtime scope
downgrade, not a compile-time rejection). The sem axis decomposes
compositionally: a "release part" contributes `MEMBAR.{SC,ALL}.<scope>`
(+`ERRBAR`+`CGAERRBAR` when scope > cta) and an "acquire part"
contributes `CCTL.IVALL` (empty at cta scope); `sc` = SC-flavoured
release part + acquire part, `acq_rel` = ALL-flavoured release part +
acquire part, `acquire`/`release` are the bare parts. `fence.acquire.cta`
lowers to zero attributable instructions (D-class). Omitting the sem
token (`fence.<scope>;`) is also legal and is byte-identical to
`fence.acq_rel.<scope>;` (default sem = acq_rel, not sc). Adjacent
fences are never merged or deduplicated, even when identical.
"""

from suite_runtime import Case, Spec

SEM_TOKENS = ("sc", "acq_rel", "acquire", "release")
SCOPE_TOKENS = ("cta", "cluster", "gpu", "sys")

PARAMS = (".param .u64 p_out",)
REGISTERS = (".reg .b64 %out;", ".reg .u32 %v;")
PREPARATION = ("ld.param.b64 %out, [p_out];", "mov.u32 %v, %tid.x;")
OBSERVATION = ("st.global.u32 [%out], %v;",)
DIRECTIVES = (".reqntid 128",)


def _fence(sem: str, scope: str, guard: str = "") -> str:
    return f"{guard}fence.{sem}.{scope};"


def _bare_fence(scope: str, guard: str = "") -> str:
    return f"{guard}fence.{scope};"


def _case(sem: str, scope: str, context: str = "baseline", target: tuple[str, ...] | None = None, extra_prep: tuple[str, ...] = (), extra_regs: tuple[str, ...] = (), guard_regs: tuple[str, ...] = (), parameters: tuple[str, ...] = PARAMS) -> Case:
    coords = {"sem": sem, "scope": scope, "context": context}
    return Case(
        "",
        coords,
        parameters=parameters,
        registers=REGISTERS + extra_regs + guard_regs,
        preparation=PREPARATION + extra_prep,
        target=target if target is not None else (_fence(sem, scope),),
        observation=OBSERVATION,
        directives=DIRECTIVES,
    )


def fence_cases() -> list[Case]:
    # SF.sem x SF.scope full factorial: all 16 combinations are legal.
    return [_case(sem, scope) for sem in SEM_TOKENS for scope in SCOPE_TOKENS]


def fence_expanded() -> list[Case]:
    cases = fence_cases()

    # CTX.spelling: omitted-sem shorthand is byte-identical to acq_rel (P0-2 alternate grammar)
    cases.append(_case("acq_rel", "cta", context="spelling_implicit_cta", target=(_bare_fence("cta"),)))
    cases.append(_case("acq_rel", "gpu", context="spelling_implicit_gpu", target=(_bare_fence("gpu"),)))

    # CTX.pre_post_global: realistic release-then-acquire pattern around a global flag
    cases.append(_case(
        "sc", "gpu", context="pre_ld_global_post_st_global",
        extra_regs=(".reg .u32 %pre; .reg .b64 %in;",),
        extra_prep=("ld.param.b64 %in, [p_in];", "ld.global.u32 %pre, [%in];", "add.u32 %v, %v, %pre;"),
        parameters=PARAMS + (".param .u64 p_in",),
    ))

    # CTX.pre_post_shared: CTA-scope fence between shared st/ld (typical intra-CTA producer/consumer)
    cases.append(_case(
        "sc", "cta", context="pre_st_shared_post_ld_shared",
        extra_regs=(".shared .align 4 .b32 slot;",),
        extra_prep=("st.shared.u32 [slot], %v;",),
        target=(_fence("sc", "cta"),),
    ))

    # CTX.atomic_adjacent: atom.global immediately before the fence
    cases.append(_case(
        "sc", "gpu", context="pre_atomic_global",
        extra_regs=(".reg .u32 %old; .reg .b64 %in;",),
        extra_prep=("ld.param.b64 %in, [p_in];", "atom.global.add.u32 %old, [%in], 1;", "add.u32 %v, %v, %old;"),
        parameters=PARAMS + (".param .u64 p_in",),
    ))

    # CTX.mixed_space: global load before, shared store after (space-mix context axis)
    cases.append(_case(
        "sc", "gpu", context="mixed_global_shared",
        extra_regs=(".reg .u32 %pre; .reg .b64 %in;", ".shared .align 4 .b32 slot2;"),
        extra_prep=("ld.param.b64 %in, [p_in];", "ld.global.u32 %pre, [%in];", "add.u32 %v, %v, %pre;"),
        parameters=PARAMS + (".param .u64 p_in",),
    ))

    # CTX.double_same_scope: adjacent identical fences -- calibrated: no merge/dedup, both fully expand
    cases.append(_case(
        "sc", "gpu", context="double_same_scope",
        target=(_fence("sc", "gpu"), _fence("sc", "gpu")),
    ))

    # CTX.double_diff_scope: adjacent fences at different scopes -- calibrated: both fully expand, no interaction
    cases.append(_case(
        "sc", "cta", context="double_diff_scope",
        target=(_fence("sc", "cta"), _fence("sc", "gpu")),
    ))

    # CTX.double_release_then_acquire: calibrated to be byte-identical to a single fence.acq_rel.gpu
    cases.append(_case(
        "release", "gpu", context="double_release_then_acquire",
        target=(_fence("release", "gpu"), _fence("acquire", "gpu")),
    ))

    # CTX.guard: predicated issue
    cases.append(_case(
        "sc", "gpu", context="guarded",
        extra_regs=(".reg .pred %p;",),
        extra_prep=("setp.lt.u32 %p, %v, 16;",),
        target=(_fence("sc", "gpu", guard="@%p "),),
    ))

    # CTX.inflight_depth: P0-1 control-word axis -- preceding independent global loads
    for depth in (2, 4):
        loads = tuple(f"ld.global.u32 %d{i}, [%in+{i * 4}];" for i in range(depth))
        merges = tuple(f"add.u32 %v, %v, %d{i};" for i in range(depth))
        regs = tuple(f".reg .u32 %d{i};" for i in range(depth))
        cases.append(_case(
            "sc", "gpu", context=f"inflight_depth_{depth}",
            extra_regs=(".reg .b64 %in;",) + regs,
            extra_prep=("ld.param.b64 %in, [p_in];",) + loads + merges,
            parameters=PARAMS + (".param .u64 p_in",),
        ))

    # CTX.kernel_template: padded signature (P1-1 axis)
    wide_params = (".param .u32 p_pad0", ".param .u64 p_out", ".param .u64 p_pad1", ".param .u32 p_pad2")
    cases.append(_case("acq_rel", "sys", context="template_wide", parameters=wide_params))

    return cases


def fence_negative() -> list[Case]:
    def probe(coords: dict, target: str, reason: str, diagnostic: str) -> Case:
        return Case("", coords, parameters=(), registers=(), preparation=(), target=(target,), observation=(), directives=(), expected="reject", reason=reason, expected_diagnostic=diagnostic)

    return [
        probe({"probe": "unknown_scope_token"}, "fence.sc.warp;", "warp is not a defined scope token", "Unknown modifier '.warp'"),
        probe({"probe": "missing_scope_bare"}, "fence;", "scope modifier is mandatory", "Scope modifier required for instruction 'fence'"),
        probe({"probe": "missing_scope_acq_rel"}, "fence.acq_rel;", "scope modifier is mandatory even with a sem token", "Modifier '.acq_rel' requires scope with 'fence' instruction"),
        probe({"probe": "unexpected_operand"}, "fence.sc.cta %r0;", "fence takes no operands", "Arguments mismatch for instruction 'fence'"),
        probe({"probe": "illegal_sem_relaxed"}, "fence.relaxed.cta;", ".relaxed is a memory-op qualifier, not a fence sem", "Illegal modifier '.relaxed' for instruction 'fence'"),
        probe({"probe": "illegal_sem_weak"}, "fence.weak.cta;", ".weak is a memory-op qualifier, not a fence sem", "Illegal modifier '.weak' for instruction 'fence'"),
        # complement sampling outside the assumed-legal surface (P0-2)
        probe({"probe": "illegal_modifier_aligned"}, "fence.sc.cta.aligned;", ".aligned exists on barrier.cluster.* but not on fence", "Illegal modifier '.aligned' for instruction 'fence'"),
        probe({"probe": "duplicate_sem_tokens"}, "fence.acquire.release.cta;", "sem tokens are a mutually exclusive singleton, not composable", "Duplicate .release modifier"),
        probe({"probe": "duplicate_scope_tokens"}, "fence.sc.cta.sc.cta;", "scope tokens are a mutually exclusive singleton", "Duplicate .sc modifier"),
    ]


FACTORS = (
    {"id": "SF.sem", "levels": ["sc", "acq_rel", "acquire", "release"]},
    {"id": "SF.scope", "levels": ["cta", "cluster", "gpu", "sys"]},
    {"id": "CTX.context", "levels": ["baseline", "spelling_implicit_cta", "spelling_implicit_gpu", "pre_ld_global_post_st_global", "pre_st_shared_post_ld_shared", "pre_atomic_global", "mixed_global_shared", "double_same_scope", "double_diff_scope", "double_release_then_acquire", "guarded", "inflight_depth_2", "inflight_depth_4", "template_wide"]},
)


def _empty_target_allowed(coordinates: dict) -> bool:
    # D-class: fence.acquire.cta lowers to zero attributable instructions.
    return coordinates.get("sem") == "acquire" and coordinates.get("scope") == "cta"


SPEC = Spec(
    family="fence",
    opcode="fence",
    ptx_opcode="fence",
    target_patterns=("MEMBAR", "ERRBAR", "CCTL.IVALL"),
    factors=FACTORS,
    syntax_cases=fence_cases,
    expanded_cases=fence_expanded,
    negative_cases=fence_negative,
    empty_target_allowed=_empty_target_allowed,
)

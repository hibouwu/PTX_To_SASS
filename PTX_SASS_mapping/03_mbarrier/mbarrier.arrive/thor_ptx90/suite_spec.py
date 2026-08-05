#!/usr/bin/env python3
"""Independent experiment definition for mbarrier.arrive on Thor.

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 / nvdisasm
V13.0.85 (`sm_110a`): the instruction always lowers to a single core
`SYNCS.ARRIVE.TRANS64` with an orthogonal suffix system --
`.A1T0` (implicit count 1) vs `.ART0` (explicit count, immediate and register
forms are SASS-identical) vs `.TMASK.ART0` (`.noComplete`, requires explicit
count and rejects `.cluster` scope) -- and an orthogonal `.RED` suffix that
appears whenever the address operand is in `.shared::cluster` (remote/DSMEM)
space, which in turn *requires* the result operand to be the sink `_`
(capturing a real token on a remote arrive is rejected). Independently again,
`sem=.release` combined with `scope=.cluster` (and only that combination)
prepends a fixed four-instruction barrier preamble
(`MEMBAR.ALL.CTA`+`MEMBAR.ALL.GPU`+`ERRBAR`+`CGAERRBAR`) before the core
arrive; `.relaxed` never triggers it, regardless of scope or address space.
State-space spelling (`.shared`, `.shared::cta`, and the no-qualifier generic
form reached via a 64-bit `mov` of the shared symbol) are SASS-identical.
Two combinations were found legal against a naive reading of the grammar and
are folded into the positive/expanded matrix rather than the negative
corpus (P0-2 discovery channel): a runtime-zero count sourced from a register
(only a literal `0` operand is statically rejected), and `.cta` scope paired
with a `.shared::cluster` (remote) address operand.
"""

from suite_runtime import Case, Spec

SPACE_TOKENS = {
    "shared": ".shared",
    "shared_cta": ".shared::cta",
    "shared_cluster": ".shared::cluster",
    "generic": "",
}

BASE_PARAMS = (".param .u64 p_out",)
INDIRECT_PARAMS = (".param .u64 p_out", ".param .u64 p_off")
WIDE_PARAMS = (".param .u32 p_pad0", ".param .u64 p_out", ".param .u64 p_pad1", ".param .u32 p_pad2")

DIRECTIVES = (".reqntid 32",)


def _arrive_instr(sem: str, scope: str, space: str, count_form: str, token: str, no_complete: bool, guard: str = "", addr_expr: str = "%addr", count_reg: str = "%n", token_reg: str = "%tok") -> str:
    if space == "shared_cluster" and token != "discard":
        raise ValueError("remote (.shared::cluster) arrive requires sink token")
    mods = []
    if no_complete:
        mods.append(".noComplete")
    if sem:
        mods.append(f".{sem}")
    if scope:
        mods.append(f".{scope}")
    mods.append(SPACE_TOKENS[space])
    dst = "_" if token == "discard" else token_reg
    tail = ""
    if count_form == "immediate":
        tail = ", 2"
    elif count_form == "register":
        tail = f", {count_reg}"
    return f"{guard}mbarrier.arrive{''.join(mods)}.b64 {dst}, [{addr_expr}]{tail};"


def _registers(remote: bool = False, generic: bool = False, count_reg: bool = False, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    regs = [
        ".shared .align 8 .b64 mbar;",
        ".reg .b64 %out, %tok;",
        ".reg .b32 %addr, %cnt, %v;",
    ]
    if remote:
        regs.append(".reg .b32 %remaddr;")
    if generic:
        regs.append(".reg .b64 %addr64;")
    if count_reg:
        regs.append(".reg .b32 %n;")
    regs.extend(extra)
    return tuple(regs)


def _preparation(remote: bool = False, generic: bool = False, count_reg: bool = False, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    prep = [
        "ld.param.b64 %out, [p_out];",
        "mov.u32 %addr, mbar;",
        "mov.u32 %cnt, 1;",
        "mbarrier.init.shared::cta.b64 [%addr], %cnt;",
        "bar.sync 0;",
    ]
    if remote:
        prep.append("mapa.shared::cluster.u32 %remaddr, %addr, 0;")
    if generic:
        prep.append("mov.u64 %addr64, mbar;")
    if count_reg:
        prep.append("mov.u32 %n, 2;")
    prep.extend(extra)
    return tuple(prep)


def _observation(token: str) -> tuple[str, ...]:
    if token == "discard":
        return ("mov.u32 %v, 1;", "st.global.u32 [%out], %v;")
    return ("st.global.u64 [%out], %tok;",)


def _coords(sem: str, scope: str, space: str, count_form: str, token: str, no_complete: bool, context: str) -> dict:
    return {"sem": sem, "scope": scope, "space": space, "count_form": count_form, "token": token, "no_complete": no_complete, "context": context}


def _case(sem: str, scope: str, space: str, count_form: str, token: str, no_complete: bool, context: str = "baseline") -> Case:
    remote = space == "shared_cluster"
    generic = space == "generic"
    count_reg = count_form == "register"
    addr_expr = "%remaddr" if remote else ("%addr64" if generic else "%addr")
    coords = _coords(sem, scope, space, count_form, token, no_complete, context)
    return Case(
        "",
        coords,
        parameters=BASE_PARAMS,
        registers=_registers(remote, generic, count_reg),
        preparation=_preparation(remote, generic, count_reg),
        target=(_arrive_instr(sem, scope, space, count_form, token, no_complete, addr_expr=addr_expr),),
        observation=_observation(token),
        directives=DIRECTIVES,
    )


def arrive_cases() -> list[Case]:
    cases = []
    # sem x scope full factorial, local shared::cta address, no count, token consumed (P0-1 core axis)
    for sem in ("release", "relaxed"):
        for scope in ("cta", "cluster"):
            cases.append(_case(sem, scope, "shared_cta", "absent", "consumed", False))
    # state-space spelling equivalence: bare .shared and no-qualifier generic (mov.u64 of the shared symbol)
    cases.append(_case("release", "cta", "shared", "absent", "consumed", False))
    cases.append(_case("release", "cta", "generic", "absent", "consumed", False))
    # remote (.shared::cluster / DSMEM) address x sem x scope full factorial; token forced to sink
    for sem in ("release", "relaxed"):
        for scope in ("cta", "cluster"):
            cases.append(_case(sem, scope, "shared_cluster", "absent", "discard", False))
    # count operand form: immediate and register are SASS-identical (.ART0)
    cases.append(_case("release", "cta", "shared_cta", "immediate", "consumed", False))
    cases.append(_case("release", "cta", "shared_cta", "register", "consumed", False))
    # token consumption: discard still emits the instruction (side-effecting), destination becomes RZ
    cases.append(_case("release", "cta", "shared_cta", "absent", "discard", False))
    # .noComplete requires an explicit count operand; immediate and register forms both calibrated
    cases.append(_case("release", "cta", "shared_cta", "register", "consumed", True))
    cases.append(_case("release", "cta", "shared_cta", "immediate", "consumed", True))
    return cases


def arrive_expanded() -> list[Case]:
    cases = arrive_cases()

    # CTX.spelling_default: sem/scope omitted entirely (default = release/cta), proves textual equivalence
    coords = _coords("", "", "shared_cta", "absent", "consumed", False, "spelling_default")
    cases.append(Case("", coords, parameters=BASE_PARAMS, registers=_registers(), preparation=_preparation(), target=(_arrive_instr("", "", "shared_cta", "absent", "consumed", False),), observation=_observation("consumed"), directives=DIRECTIVES))

    # CTX.mbar_derived: address produced by non-trivial arithmetic, not the raw symbol register (P1-2)
    coords = _coords("release", "cta", "shared_cta", "absent", "consumed", False, "mbar_derived")
    extra_regs = (".reg .b32 %addr2;",)
    extra_prep = ("add.u32 %addr2, %addr, 0;",)
    cases.append(Case("", coords, parameters=BASE_PARAMS, registers=_registers(extra=extra_regs), preparation=_preparation(extra=extra_prep), target=(_arrive_instr("release", "cta", "shared_cta", "absent", "consumed", False, addr_expr="%addr2"),), observation=_observation("consumed"), directives=DIRECTIVES))

    # CTX.count_indirect: count value loaded from global memory, not foldable at compile time (P1-2)
    coords = _coords("release", "cta", "shared_cta", "register", "consumed", False, "count_indirect")
    extra_regs = (".reg .b64 %offptr;", ".reg .b32 %n2;")
    extra_prep = ("ld.param.b64 %offptr, [p_off];", "ld.global.u32 %n2, [%offptr];")
    cases.append(Case("", coords, parameters=INDIRECT_PARAMS, registers=_registers(count_reg=True, extra=extra_regs), preparation=_preparation(count_reg=True, extra=extra_prep), target=(_arrive_instr("release", "cta", "shared_cta", "register", "consumed", False, count_reg="%n2"),), observation=_observation("consumed"), directives=DIRECTIVES))

    # CTX.guarded: predicated issue (calibrated: O0 branches, O3 collapses to uniform @!UPx)
    coords = _coords("release", "cta", "shared_cta", "absent", "consumed", False, "guarded")
    extra_regs = (".reg .b32 %t0;", ".reg .pred %p;")
    extra_prep = ("mov.u32 %t0, %tid.x;", "setp.lt.u32 %p, %t0, 1;")
    cases.append(Case("", coords, parameters=BASE_PARAMS, registers=_registers(extra=extra_regs), preparation=_preparation(extra=extra_prep), target=(_arrive_instr("release", "cta", "shared_cta", "absent", "consumed", False, guard="@%p "),), observation=_observation("consumed"), directives=DIRECTIVES))

    # CTX.inflight_depth_{2,4}: independent barriers arriving back-to-back (P0-1 scoreboard/control axis)
    for depth in (2, 4):
        bar_decls = tuple(f".shared .align 8 .b64 mbar{i};" for i in range(depth))
        addr_regs = ", ".join(f"%addr{i}" for i in range(depth))
        tok_regs = ", ".join(f"%tok{i}" for i in range(depth))
        regs = [f".reg .b32 {addr_regs}, %cnt;", f".reg .b64 %out, {tok_regs}, %tokx;"]
        prep = ["ld.param.b64 %out, [p_out];", "mov.u32 %cnt, 1;"]
        prep.extend(f"mov.u32 %addr{i}, mbar{i};" for i in range(depth))
        prep.extend(f"mbarrier.init.shared::cta.b64 [%addr{i}], %cnt;" for i in range(depth))
        prep.append("bar.sync 0;")
        targets = tuple(
            _arrive_instr("release", "cta", "shared_cta", "absent", "consumed", False, addr_expr=f"%addr{i}", token_reg=f"%tok{i}")
            for i in range(depth)
        )
        observation = ["xor.b64 %tokx, %tok0, %tok1;"]
        observation.extend(f"xor.b64 %tokx, %tokx, %tok{i};" for i in range(2, depth))
        observation.append("st.global.u64 [%out], %tokx;")
        coords = _coords("release", "cta", "shared_cta", "absent", "consumed", False, f"inflight_depth_{depth}")
        cases.append(Case("", coords, parameters=BASE_PARAMS, declarations=(), registers=bar_decls + tuple(regs), preparation=tuple(prep), target=targets, observation=tuple(observation), directives=DIRECTIVES))

    # CTX.template_wide: padded kernel signature (P1-1); calibrated null result -- mbar is a static
    # shared symbol, not parameter-derived, so this instruction is insensitive to param-bank layout.
    coords = _coords("release", "cta", "shared_cta", "absent", "consumed", False, "template_wide")
    cases.append(Case("", coords, parameters=WIDE_PARAMS, registers=_registers(), preparation=_preparation(), target=(_arrive_instr("release", "cta", "shared_cta", "absent", "consumed", False),), observation=_observation("consumed"), directives=DIRECTIVES))

    # CTX.complement_count_zero_register (P0-2 discovery): a runtime-zero count sourced from a
    # register compiles and emits a normal .ART0 arrive; only a literal `0` operand is rejected
    # (see negative probe `count_immediate_zero`). Folded into the positive matrix per project
    # convention: "predicted illegal but accepted" is a discovery channel, not a negative case.
    coords = _coords("release", "cta", "shared_cta", "register", "consumed", False, "complement_count_zero_register")
    extra_regs = (".reg .b32 %nzero;",)
    extra_prep = ("mov.u32 %nzero, 0;",)
    cases.append(Case("", coords, parameters=BASE_PARAMS, registers=_registers(extra=extra_regs), preparation=_preparation(extra=extra_prep), target=(_arrive_instr("release", "cta", "shared_cta", "register", "consumed", False, count_reg="%nzero"),), observation=_observation("consumed"), directives=DIRECTIVES))

    # CTX.complement_cta_scope_remote (P0-2 discovery): .cta scope paired with a .shared::cluster
    # (remote) address looks self-contradictory by naive reading but is accepted; the barrier
    # preamble trigger (sem=release & scope=cluster) and the .RED suffix trigger (remote address)
    # are independent conditions, confirmed here by decoupling them.
    cases.append(_case("release", "cta", "shared_cluster", "absent", "discard", False, context="complement_cta_scope_remote"))

    return cases


def arrive_negative() -> list[Case]:
    def probe(coords: dict, target: str, reason: str, diagnostic: str, *, remote: bool = False) -> Case:
        return Case("", coords, parameters=BASE_PARAMS, registers=_registers(remote=remote), preparation=_preparation(remote=remote), target=(target,), observation=(), directives=DIRECTIVES, expected="reject", reason=reason, expected_diagnostic=diagnostic)

    return [
        probe({"probe": "global_space"}, "mbarrier.arrive.global.b64 %tok, [%addr];", "arrive requires shared or generic addressing, not .global", "State space incorrect for instruction 'mbarrier.arrive'"),
        probe({"probe": "acquire_sem"}, "mbarrier.arrive.acquire.shared::cta.b64 %tok, [%addr];", "arrive only accepts .release/.relaxed, not .acquire", "Illegal modifier '.acquire' for instruction 'mbarrier.arrive'"),
        probe({"probe": "count_immediate_zero"}, "mbarrier.arrive.shared::cta.b64 %tok, [%addr], 0;", "a literal zero count operand is statically rejected", "value '0' expected to be a non-zero positive"),
        probe({"probe": "token_type_mismatch"}, "mbarrier.arrive.shared::cta.b64 %v, [%addr];", "token result must be .b64, not the .b32 %v declared here", "Arguments mismatch for instruction 'mbarrier.arrive'"),
        probe({"probe": "nocomplete_cluster_scope"}, "mbarrier.arrive.noComplete.release.cluster.shared::cta.b64 %tok, [%addr], 2;", ".noComplete is incompatible with .cluster scope", "Modifier '.cluster' cannot be combined with modifier '.noComplete'"),
        probe({"probe": "nocomplete_missing_count"}, "mbarrier.arrive.noComplete.shared::cta.b64 %tok, [%addr];", ".noComplete requires an explicit count operand", "Illegal modifier '.noComplete' for instruction 'mbarrier.arrive without count argument'"),
        probe({"probe": "remote_real_token"}, "mbarrier.arrive.release.cluster.shared::cluster.b64 %tok, [%remaddr];", "remote (.shared::cluster) arrive must use sink '_', not a real token destination", "Sink '_' is expected as a destination operand for instruction 'mbarrier.arrive' with '.shared::cluster'", remote=True),
    ]


FACTORS = (
    {"id": "SF.sem", "levels": ["release", "relaxed"]},
    {"id": "SF.scope", "levels": ["cta", "cluster"]},
    {"id": "SF.space", "levels": ["shared", "shared_cta", "shared_cluster", "generic"]},
    {"id": "SF.count_form", "levels": ["absent", "immediate", "register"]},
    {"id": "SF.token", "levels": ["consumed", "discard"]},
    {"id": "SF.no_complete", "levels": [False, True]},
    {"id": "CTX.context", "levels": ["baseline", "spelling_default", "mbar_derived", "count_indirect", "guarded", "inflight_depth_2", "inflight_depth_4", "template_wide", "complement_count_zero_register", "complement_cta_scope_remote"]},
)

SPEC = Spec(
    family="mbarrier",
    opcode="arrive",
    ptx_opcode="mbarrier.arrive",
    target_patterns=("SYNCS.ARRIVE.TRANS64",),
    factors=FACTORS,
    syntax_cases=arrive_cases,
    expanded_cases=arrive_expanded,
    negative_cases=arrive_negative,
    empty_target_allowed=lambda _coordinates: False,
)

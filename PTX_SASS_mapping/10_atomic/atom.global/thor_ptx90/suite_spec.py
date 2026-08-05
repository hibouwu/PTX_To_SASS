#!/usr/bin/env python3
"""Independent experiment definition for atom.global on Thor.

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 (`sm_110a`): op x type maps to ATOMG.E.<OP>[.<TYPE-SUFFIX>]
[.STRONG.<SCOPE-SUFFIX>] (scope suffix: none/.cluster/.gpu -> GPU, .cta ->
SM, .sys -> SYS); .release/.acq_rel prepend a MEMBAR.ALL.<SCOPE> before the
ATOMG (.relaxed/.acquire add nothing over the bare form). The central
falsifiable claim for this family: when an atom's destination register is
dead, ptxas silently downgrades ATOMG -> REDG for every op that has a
red-legal counterpart (add/min/max/and/or/xor/inc/dec); `.exch` and `.cas`
have no `red` form (confirmed: `red.global.exch`/`red.global.cas` are
`Illegal operation` diagnostics) so a dead-result exch/cas instead keeps the
ATOMG mnemonic and simply retargets the destination to RZ. `red.global.<op>`
compiles to byte-identical REDG as the dead-atom downgrade. See
`../../实验设计.md` for the full calibration record and probe transcripts.
"""

from suite_runtime import Case, Spec

PARAMS = (".param .u64 p_addr", ".param .u64 p_out")
PARAMS_VAL = (".param .u64 p_addr", ".param .u64 p_out", ".param .u64 p_val")
PARAMS_WIDE = (".param .u32 p_pad0", ".param .u64 p_addr", ".param .u64 p_pad1", ".param .u64 p_out", ".param .u32 p_pad2")

# PTX type token -> register storage type. f16x2/bf16x2 are carried in .b32
# registers (packed-pair bit pattern); everything else stores in its own type.
REG_TYPE = {
    "u32": "u32", "u64": "u64", "s32": "s32", "s64": "s64",
    "f32": "f32", "f64": "f64", "b32": "b32", "b64": "b64", "b16": "b16",
    "f16x2": "b32", "bf16x2": "b32",
}

# Calibrated op x type legal surface for atom.global (28 combos). Types not
# listed were probed and rejected; see 实验设计.md's 校准表 for the exact
# diagnostics (e.g. add.b32, and.u32, min.f32, exch.u32, inc.s32 all reject).
LEGAL_OP_TYPES = {
    "add": ("u32", "u64", "s32", "f32", "f64", "f16x2", "bf16x2"),
    "min": ("u32", "u64", "s32", "s64"),
    "max": ("u32", "u64", "s32", "s64"),
    "and": ("b32", "b64"),
    "or": ("b32", "b64"),
    "xor": ("b32", "b64"),
    "exch": ("b32", "b64"),
    "cas": ("b32", "b64", "b16"),
    "inc": ("u32",),
    "dec": ("u32",),
}

FLOAT_NOFTZ_TYPES = ("f16", "f16x2", "bf16", "bf16x2")


def _imm(ty: str) -> str:
    return "1.0" if ty in ("f32", "f64") else "1"


def _addr_prep_indirect() -> tuple[str, ...]:
    """Register + offset address form: base parameter offset by %tid.x*8.

    This is the default address shape for the syntax matrix. A uniform
    (parameter-direct) address instead triggers a warp-aggregation rewrite
    at O3 (see CTX.address_direct in the expanded set) that adds VOTEU/POPC/
    SHFL scaffolding around the same ATOMG -- confirmed by probe, not by
    reading the PTX ISA guide.
    """
    return (
        "ld.param.u64 %base, [p_addr];",
        "ld.param.u64 %out, [p_out];",
        "mov.u32 %t0, %tid.x;",
        "cvt.u64.u32 %toff, %t0;",
        "shl.b64 %toff, %toff, 3;",
        "add.u64 %addr, %base, %toff;",
    )


def _atom_instr(op: str, ty: str, mod: str = "", dst: str = "%d", addr: str = "%addr", val: str = "%b", cmp_reg: str = "%c") -> str:
    noftz = ".noftz" if ty in FLOAT_NOFTZ_TYPES else ""
    if op == "cas":
        return f"atom{mod}.global.cas.{ty} {dst}, [{addr}], {cmp_reg}, {val};"
    return f"atom{mod}.global.{op}{noftz}.{ty} {dst}, [{addr}], {val};"


def _syntax_case(op: str, ty: str) -> Case:
    rty = REG_TYPE[ty]
    coords = {"op": op, "type": ty, "result_use": "live", "sem": "none", "scope": "none", "address_form": "indirect", "context": "baseline"}
    registers = [
        ".reg .u64 %base, %addr, %out, %toff;",
        ".reg .u32 %t0;",
        f".reg .{rty} %d, %b;",
    ]
    prep = list(_addr_prep_indirect())
    if op == "cas":
        registers.append(f".reg .{rty} %c;")
        prep.append(f"mov.{rty} %c, {_imm(ty)};")
        prep.append(f"mov.{rty} %b, {_imm(ty)};")
    else:
        prep.append(f"mov.{rty} %b, {_imm(ty)};")
    target = (_atom_instr(op, ty),)
    observation = (f"st.global.{rty} [%out], %d;",)
    return Case("", coords, parameters=PARAMS, registers=tuple(registers), preparation=tuple(prep), target=target, observation=observation, directives=(".reqntid 64",))


def atom_global_cases() -> list[Case]:
    cases = []
    for op, types in LEGAL_OP_TYPES.items():
        for ty in types:
            cases.append(_syntax_case(op, ty))
    return cases


def _ctx_case(context: str, op: str, ty: str, *, sem: str = "", scope: str = "", dead: bool = False, addr_form: str = "indirect", parameters: tuple[str, ...] = PARAMS, registers_extra: tuple[str, ...] = (), preparation_extra: tuple[str, ...] = (), target_override: tuple[str, ...] | None = None, observation_override: tuple[str, ...] | None = None, addr_reg: str = "%addr", directives: tuple[str, ...] = (".reqntid 64",)) -> Case:
    rty = REG_TYPE[ty]
    mod = f"{('.' + sem) if sem else ''}{('.' + scope) if scope else ''}"
    coords = {"op": op, "type": ty, "result_use": "dead" if dead else "live", "sem": sem or "none", "scope": scope or "none", "address_form": addr_form, "context": context}
    registers = [
        ".reg .u64 %base, %addr, %out, %toff;",
        ".reg .u32 %t0;",
        f".reg .{rty} %d, %b;",
        *registers_extra,
    ]
    prep = list(_addr_prep_indirect()) if addr_form == "indirect" else ["ld.param.u64 %base, [p_addr];", "ld.param.u64 %out, [p_out];", "add.u64 %addr, %base, 0;"]
    prep.append(f"mov.{rty} %b, {_imm(ty)};")
    prep.extend(preparation_extra)
    target = target_override if target_override is not None else (_atom_instr(op, ty, mod=mod, addr=addr_reg),)
    if observation_override is not None:
        observation = observation_override
    elif dead:
        observation = ()
    else:
        observation = (f"st.global.{rty} [%out], %d;",)
    return Case("", coords, parameters=parameters, registers=tuple(registers), preparation=tuple(prep), target=target, observation=observation, directives=directives)


def atom_global_expanded() -> list[Case]:
    cases = []

    # --- CTX.result_use: dead-result downgrade (core hypothesis) ---
    # add/min/and/or/inc: no live consumer of %d -> ATOMG downgrades to REDG.
    cases.append(_ctx_case("result_dead_add_u32", "add", "u32", dead=True))
    cases.append(_ctx_case("result_dead_min_s32", "min", "s32", dead=True))
    cases.append(_ctx_case("result_dead_and_b32", "and", "b32", dead=True))
    cases.append(_ctx_case("result_dead_or_b64", "or", "b64", dead=True))
    cases.append(_ctx_case("result_dead_inc_u32", "inc", "u32", dead=True))
    # exch/cas: no red.global counterpart exists (Illegal operation), so a
    # dead result must stay ATOMG with destination retargeted to RZ instead
    # of downgrading -- this is the falsifying counter-case for a naive
    # "every dead atom becomes red" rule.
    cases.append(_ctx_case("result_dead_exch_b32", "exch", "b32", dead=True))
    registers_cas_dead = (".reg .b32 %c;",)
    cases.append(_ctx_case("result_dead_cas_b32", "cas", "b32", dead=True, registers_extra=registers_cas_dead, preparation_extra=("mov.b32 %c, 1;",)))

    # --- CTX.address_form: parameter-direct (warp-uniform) vs register+offset ---
    # Direct/uniform address triggers a warp-aggregation rewrite at O3
    # (VOTEU.ANY / FLO.U32 / POPC / SHFL.IDX around a single leader ATOMG)
    # that is entirely absent from the register+offset baseline above.
    cases.append(_ctx_case("address_direct_add_u32", "add", "u32", addr_form="direct"))

    # --- CTX.producer: non-foldable address and value sources (P1-2) ---
    cases.append(Case(
        "", {"op": "add", "type": "u32", "result_use": "live", "sem": "none", "scope": "none", "address_form": "indirect_producer", "context": "address_indirect_producer"},
        parameters=PARAMS, registers=(".reg .u64 %base, %addrptr, %addr, %out;", ".reg .u32 %d, %b;"),
        preparation=("ld.param.u64 %base, [p_addr];", "ld.param.u64 %out, [p_out];", "ld.global.u64 %addr, [%base];", "mov.u32 %b, 1;"),
        target=(_atom_instr("add", "u32"),), observation=("st.global.u32 [%out], %d;",), directives=(".reqntid 64",),
    ))
    cases.append(Case(
        "", {"op": "add", "type": "u32", "result_use": "live", "sem": "none", "scope": "none", "address_form": "indirect", "context": "value_indirect_producer"},
        parameters=PARAMS_VAL, registers=(".reg .u64 %base, %valptr, %addr, %out;", ".reg .u32 %d, %b;"),
        preparation=("ld.param.u64 %base, [p_addr];", "ld.param.u64 %out, [p_out];", "ld.param.u64 %valptr, [p_val];", "add.u64 %addr, %base, 0;", "ld.global.u32 %b, [%valptr];"),
        target=(_atom_instr("add", "u32"),), observation=("st.global.u32 [%out], %d;",), directives=(".reqntid 64",),
    ))

    # --- CTX.inflight: two atoms in one scheduling region (P0-1 axis) ---
    # same address (aliasing) vs distinct addresses (plain depth-2).
    cases.append(Case(
        "", {"op": "add", "type": "u32", "result_use": "live", "sem": "none", "scope": "none", "address_form": "indirect", "context": "dual_atom_same_address"},
        parameters=PARAMS, registers=(".reg .u64 %base, %addr, %out, %toff;", ".reg .u32 %t0, %d1, %d2, %b, %merge;"),
        preparation=(*_addr_prep_indirect(), "mov.u32 %b, 1;"),
        target=("atom.global.add.u32 %d1, [%addr], %b;", "atom.global.add.u32 %d2, [%addr], %b;"),
        observation=("xor.b32 %merge, %d1, %d2;", "st.global.u32 [%out], %merge;"), directives=(".reqntid 64",),
    ))
    cases.append(Case(
        "", {"op": "add", "type": "u32", "result_use": "live", "sem": "none", "scope": "none", "address_form": "indirect", "context": "inflight_depth_2_distinct_address"},
        parameters=PARAMS, registers=(".reg .u64 %base, %addr, %addr2, %out, %toff;", ".reg .u32 %t0, %d1, %d2, %b, %merge;"),
        preparation=(*_addr_prep_indirect(), "add.u64 %addr2, %addr, 256;", "mov.u32 %b, 1;"),
        target=("atom.global.add.u32 %d1, [%addr], %b;", "atom.global.add.u32 %d2, [%addr2], %b;"),
        observation=("xor.b32 %merge, %d1, %d2;", "st.global.u32 [%out], %merge;"), directives=(".reqntid 64",),
    ))

    # --- CTX.guard: predicated issue ---
    cases.append(Case(
        "", {"op": "add", "type": "u32", "result_use": "live", "sem": "none", "scope": "none", "address_form": "indirect", "context": "guarded"},
        parameters=PARAMS, registers=(".reg .u64 %base, %addr, %out, %toff;", ".reg .u32 %t0, %d, %b;", ".reg .pred %p;"),
        preparation=(*_addr_prep_indirect(), "mov.u32 %b, 1;", "setp.lt.u32 %p, %t0, 32;"),
        target=("@%p atom.global.add.u32 %d, [%addr], %b;",), observation=("st.global.u32 [%out], %d;",), directives=(".reqntid 64",),
    ))

    # --- CTX.template_wide: padded kernel signature (P1-1 axis) ---
    cases.append(_ctx_case("template_wide", "add", "u32", parameters=PARAMS_WIDE))

    # --- CTX.cas_predicate_consumer: compare-exchange feeding a branch ---
    cases.append(Case(
        "", {"op": "cas", "type": "b32", "result_use": "live", "sem": "none", "scope": "none", "address_form": "indirect", "context": "cas_predicate_consumer"},
        parameters=PARAMS, registers=(".reg .u64 %base, %addr, %out, %toff;", ".reg .u32 %t0, %d, %cmp, %swap, %v;", ".reg .pred %p;"),
        preparation=(*_addr_prep_indirect(), "mov.u32 %cmp, 0;", "mov.u32 %swap, 1;"),
        target=("atom.global.cas.b32 %d, [%addr], %cmp, %swap;",),
        observation=("setp.eq.u32 %p, %d, %cmp;", "@%p bra L_cas_pred_done;", "mov.u32 %v, 7;", "st.global.u32 [%out], %v;", "L_cas_pred_done:",),
        directives=(".reqntid 64",),
    ))

    # --- CTX.sem_scope: modifier-chain sampling (t=2-ish over 5 sem x 4 scope) ---
    cases.append(_ctx_case("sem_scope_acquire_cta", "add", "u32", sem="acquire", scope="cta"))
    cases.append(_ctx_case("sem_scope_release_gpu", "add", "u32", sem="release", scope="gpu"))
    cases.append(_ctx_case("sem_scope_acqrel_sys", "add", "u32", sem="acq_rel", scope="sys"))
    cases.append(_ctx_case("sem_scope_relaxed_cluster", "add", "u32", sem="relaxed", scope="cluster"))
    cases.append(_ctx_case("sem_scope_release_cta", "add", "u32", sem="release", scope="cta"))
    cases.append(_ctx_case("sem_scope_none_sys", "add", "u32", scope="sys"))

    # --- CTX.structural: scalar fp16 add has no native RMW -> compiler
    # synthesizes a CAS retry loop (compiler-synthesized protocol, tcgen05
    # taxonomy class B) instead of a single ATOMG.ADD like the .f16x2 form.
    cases.append(Case(
        "", {"op": "add", "type": "f16", "result_use": "live", "sem": "none", "scope": "none", "address_form": "indirect", "context": "scalar_f16_add_cas_synthesis"},
        parameters=PARAMS, registers=(".reg .u64 %base, %addr, %out, %toff;", ".reg .u32 %t0;", ".reg .b16 %d, %b;"),
        preparation=(*_addr_prep_indirect(), "mov.b16 %b, 1;"),
        target=("atom.global.add.noftz.f16 %d, [%addr], %b;",), observation=("st.global.b16 [%out], %d;",), directives=(".reqntid 64",),
    ))

    # --- CTX.vector: min/max on packed fp16-family require a .v2/.v4/.v8
    # vector modifier distinct from the plain .f16x2 packed-pair type; this
    # sample uses .v4.f16 (4 independent half-precision lanes, 64-bit op).
    cases.append(Case(
        "", {"op": "min", "type": "f16", "result_use": "live", "sem": "none", "scope": "none", "address_form": "indirect", "context": "min_vector_v4_f16"},
        parameters=PARAMS, registers=(".reg .u64 %base, %addr, %out, %toff;", ".reg .u32 %t0;", ".reg .b16 %d0, %d1, %d2, %d3, %b0, %b1, %b2, %b3;"),
        preparation=(*_addr_prep_indirect(), "mov.b16 %b0, 1;", "mov.b16 %b1, 1;", "mov.b16 %b2, 1;", "mov.b16 %b3, 1;"),
        target=("atom.global.min.noftz.v4.f16 {%d0, %d1, %d2, %d3}, [%addr], {%b0, %b1, %b2, %b3};",),
        observation=("st.global.b16 [%out], %d0;",), directives=(".reqntid 64",),
    ))

    # --- CTX.spelling: scope modifier accepted before the state-space token ---
    cases.append(Case(
        "", {"op": "add", "type": "u32", "result_use": "live", "sem": "none", "scope": "cluster", "address_form": "indirect", "context": "spelling_scope_before_space"},
        parameters=PARAMS, registers=(".reg .u64 %base, %addr, %out, %toff;", ".reg .u32 %t0, %d, %b;"),
        preparation=(*_addr_prep_indirect(), "mov.u32 %b, 1;"),
        target=("atom.cluster.global.add.u32 %d, [%addr], %b;",), observation=("st.global.u32 [%out], %d;",), directives=(".reqntid 64",),
    ))

    return cases


def atom_global_negative() -> list[Case]:
    def probe(coords: dict, target: str, reason: str, diagnostic: str, extra_registers: tuple[str, ...] = ()) -> Case:
        registers = (".reg .u64 %base, %addr, %out;", ".reg .u32 %t0, %d32, %b32;", ".reg .u64 %d64, %b64;", ".reg .b16 %d16, %b16;", ".reg .f32 %d32f, %b32f;", *extra_registers)
        preparation = ("ld.param.u64 %base, [p_addr];", "ld.param.u64 %out, [p_out];", "add.u64 %addr, %base, 0;", "mov.u32 %b32, 1;", "mov.u64 %b64, 1;", "mov.b16 %b16, 1;", "mov.f32 %b32f, 1.0;")
        return Case("", coords, parameters=PARAMS, registers=registers, preparation=preparation, target=(target,), observation=(), directives=(), expected="reject", reason=reason, expected_diagnostic=diagnostic)

    return [
        # op x type boundary (P0-2 primary diagnostics)
        probe({"probe": "and_wrong_type_u32"}, "atom.global.and.u32 %d32, [%addr], %b32;", ".and requires .b32/.b64, not .u32", "Operation .and requires .b32 or .b64 type for instruction 'atom'"),
        probe({"probe": "min_wrong_type_f32"}, "atom.global.min.f32 %d32f, [%addr], %b32f;", "no scalar .f32 for .min on this arch (needs vector fp16-family or int)", "Operation .min requires"),
        probe({"probe": "exch_wrong_type_u32"}, "atom.global.exch.u32 %d32, [%addr], %b32;", ".exch requires .b32/.b64/.b128, not .u32", "Operation .exch requires .b32 or .b64 or .b128 type for instruction 'atom'"),
        probe({"probe": "add_wrong_type_b32"}, "atom.global.add.b32 %d32, [%addr], %b32;", ".add is typed (u32/s32/u64/f64/f16.../f32/bf16...), not bitwise .b32", "Operation .add requires"),
        probe({"probe": "inc_wrong_type_s32"}, "atom.global.inc.s32 %d32, [%addr], %b32;", ".inc requires .u32 only", "Operation .inc requires .u32 type for instruction 'atom'"),
        probe({"probe": "dec_wrong_type_b64"}, "atom.global.dec.b64 %d64, [%addr], %b64;", ".dec requires .u32 only", "Operation .dec requires .u32 type for instruction 'atom'"),
        # operand-count / cas grammar
        probe({"probe": "cas_missing_swap_operand"}, "atom.global.cas.b32 %d32, [%addr], %b32;", "cas needs both compare and swap operands", "Arguments mismatch for instruction 'atom'"),
        # modifier-chain grammar: acquire+release written separately is not
        # the same token as .acq_rel
        probe({"probe": "acquire_release_not_acqrel"}, "atom.acquire.release.global.add.u32 %d32, [%addr], %b32;", ".acquire and .release cannot both be written; must spell .acq_rel", "Duplicate .release modifier"),
        # complement sampling outside the assumed-legal surface (P0-2 quadrant 3 candidates)
        probe({"probe": "mmio_modifier_illegal"}, "atom.mmio.relaxed.sys.global.add.u32 %d32, [%addr], %b32;", "complement: .mmio is not a legal atom modifier on this arch/order", "Illegal modifier '.mmio' for instruction 'atom'"),
        probe({"probe": "weak_modifier_illegal"}, "atom.weak.global.add.u32 %d32, [%addr], %b32;", "complement: .weak is not a spelled PTX atom memory-order token", "Illegal modifier '.weak' for instruction 'atom'"),
        probe({"probe": "min_v3_illegal_width"}, "atom.global.min.noftz.v3.f16 {%d16, %d16, %d16}, [%addr], {%b16, %b16, %b16};", "complement: vector width for packed fp16 min/max is v2/v4/v8, not v3", "Illegal vector size: 3"),
    ]


FACTORS = (
    {"id": "SF.op", "levels": ["add", "min", "max", "and", "or", "xor", "exch", "cas", "inc", "dec"]},
    {"id": "SF.type", "levels": ["u32", "u64", "s32", "s64", "f32", "f64", "f16", "f16x2", "bf16", "bf16x2", "b32", "b64", "b16"]},
    {"id": "SF.result_use", "levels": ["live", "dead"]},
    {"id": "SF.sem", "levels": ["none", "relaxed", "acquire", "release", "acq_rel"]},
    {"id": "SF.scope", "levels": ["none", "cta", "cluster", "gpu", "sys"]},
    {"id": "SF.address_form", "levels": ["indirect", "direct", "indirect_producer"]},
    {"id": "CTX.context", "levels": [
        "baseline", "result_dead_add_u32", "result_dead_min_s32", "result_dead_and_b32", "result_dead_or_b64",
        "result_dead_inc_u32", "result_dead_exch_b32", "result_dead_cas_b32", "address_direct_add_u32",
        "address_indirect_producer", "value_indirect_producer", "dual_atom_same_address",
        "inflight_depth_2_distinct_address", "guarded", "template_wide", "cas_predicate_consumer",
        "sem_scope_acquire_cta", "sem_scope_release_gpu", "sem_scope_acqrel_sys", "sem_scope_relaxed_cluster",
        "sem_scope_release_cta", "sem_scope_none_sys", "scalar_f16_add_cas_synthesis", "min_vector_v4_f16",
        "spelling_scope_before_space",
    ]},
)

SPEC = Spec(
    family="atomic",
    opcode="global",
    ptx_opcode="atom.global",
    target_patterns=("ATOMG", "REDG"),
    factors=FACTORS,
    syntax_cases=atom_global_cases,
    expanded_cases=atom_global_expanded,
    negative_cases=atom_global_negative,
    empty_target_allowed=lambda _coordinates: False,
)

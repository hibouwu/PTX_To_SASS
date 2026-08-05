#!/usr/bin/env python3
"""Independent experiment definition for mapa on Thor.

Pre-calibration verdict (ptxas V13.0.88 / nvdisasm V13.0.85, `sm_110a`):
cluster/DSMEM PTX constructs ARE accepted by the Thor toolchain (`mapa`,
`getctarank`, `ld/st.shared::cluster`, `isspacep.shared::cluster`,
`cvta.to.shared::cluster`, `%clusterid` all compile). But `mapa` has **no
dedicated MAPA SASS opcode** on this target: it is synthesized inline as
`S2R Rd, SR_CgaCtaId` (own rank-in-cluster) + `LEA` (fold in the 0x400-class
shared-memory base offset, shifted into byte 3) + `PRMT Rd, rank, 0x654, Rd`
(graft the *target* rank byte over byte 3 of the template). This holds across
O0-O3, immediate/register/indirect rank sources, u32/u64 result type, and
guarded issue. `S2R SR_CgaCtaId` alone is NOT a safe target pattern: it also
appears whenever a kernel launched with `.reqnctapercluster` merely takes the
address of a plain `.shared` symbol (even a bare `ld.shared`/`st.shared` with
no `mapa` involved needs the own-CTA-rank tag folded into the canonical
32-bit shared address on this target -- see `实验设计.md` P0-1). `PRMT` is the
unique, uncontaminated anchor (verified zero-hit on scaffolds mirroring every
context axis below, at O0-O3): only `mapa`'s rank-graft step emits it.

Confirmed operand rules: rank (`b`) is *always* `.u32` regardless of the
`.type` modifier (`.u32`/`.u64`) on `d`/`a`; `.reqnctapercluster` is not
statically enforced by ptxas; `mapa` performs no address-provenance check (an
arbitrary 32-bit register is accepted as `a`) and no compile-time bound check
on the rank immediate; `d`/`a` aliasing is accepted. These accepted-but-
questionable forms are recorded as expanded (positive) cases per the P0-2
"predicted illegal but accepted -> promote to positive matrix" rule, not as
negative probes (they would fail `check_negative`, which requires actual
rejection).
"""

from suite_runtime import Case, Spec

TYPE_REG = {"u32": "b32", "u64": "b64"}
PARAMS_OUT = (".param .u64 p_out",)
PARAMS_OUT_RANK = (".param .u64 p_out", ".param .u64 p_rank")
PARAMS_OUT_OFF = (".param .u64 p_out", ".param .u64 p_off")
DIRECTIVES = (".reqnctapercluster 2",)
SHARED_DECL = ".shared .align 8 .b8 smem[64];"


def _mapa_instr(type_: str, dst: str, addr: str, rank: str, guard: str = "") -> str:
    return f"{guard}mapa.shared::cluster.{type_} {dst}, {addr}, {rank};"


def _store(type_: str, reg: str = "%dst") -> str:
    return f"st.global.{type_} [%out], {reg};"


def _syntax_immediate_case(type_: str, rank_value: int) -> Case:
    reg = TYPE_REG[type_]
    coords = {"type": type_, "rank_source": "immediate", "rank_value": rank_value, "addr_source": "symbol_direct", "context": "baseline"}
    registers = (SHARED_DECL, f".reg .{reg} %addr, %dst;", ".reg .b32 %rank;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", f"mov.{type_} %addr, smem;", f"mov.u32 %rank, {rank_value};")
    return Case("", coords, parameters=PARAMS_OUT, registers=registers, preparation=preparation, target=(_mapa_instr(type_, "%dst", "%addr", "%rank"),), observation=(_store(type_),), directives=DIRECTIVES)


def _syntax_register_case(type_: str) -> Case:
    reg = TYPE_REG[type_]
    coords = {"type": type_, "rank_source": "register", "rank_value": None, "addr_source": "symbol_direct", "context": "baseline"}
    registers = (SHARED_DECL, f".reg .{reg} %addr, %dst;", ".reg .b32 %rank, %t0;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", f"mov.{type_} %addr, smem;", "mov.u32 %t0, %tid.x;", "and.b32 %rank, %t0, 1;")
    return Case("", coords, parameters=PARAMS_OUT, registers=registers, preparation=preparation, target=(_mapa_instr(type_, "%dst", "%addr", "%rank"),), observation=(_store(type_),), directives=DIRECTIVES)


def mapa_cases() -> list[Case]:
    cases = []
    for type_ in ("u32", "u64"):
        for rank_value in (0, 1, 3, 7):
            cases.append(_syntax_immediate_case(type_, rank_value))
        cases.append(_syntax_register_case(type_))
    return cases


def _context_case(type_: str, context: str, registers_extra: tuple[str, ...], preparation_extra: tuple[str, ...], target: tuple[str, ...], parameters: tuple[str, ...] = PARAMS_OUT, observation: tuple[str, ...] | None = None, directives: tuple[str, ...] = DIRECTIVES) -> Case:
    reg = TYPE_REG[type_]
    coords = {"type": type_, "rank_source": "register", "rank_value": None, "addr_source": "symbol_direct", "context": context}
    registers = (SHARED_DECL, f".reg .{reg} %addr, %dst;", ".reg .b32 %rank;", ".reg .b64 %out;", *registers_extra)
    preparation = ("ld.param.b64 %out, [p_out];", f"mov.{type_} %addr, smem;", *preparation_extra)
    obs = observation if observation is not None else (_store(type_),)
    return Case("", coords, parameters=parameters, registers=registers, preparation=preparation, target=target, observation=obs, directives=directives)


def mapa_expanded() -> list[Case]:
    cases = mapa_cases()

    # CTX.rank_indirect_producer: rank loaded from global memory, not foldable (P1-2)
    for type_ in ("u32", "u64"):
        case = _context_case(
            type_, "rank_indirect_producer",
            (".reg .b64 %prank;",),
            ("ld.param.b64 %prank, [p_rank];", "ld.global.u32 %rank, [%prank];"),
            (_mapa_instr(type_, "%dst", "%addr", "%rank"),),
            parameters=PARAMS_OUT_RANK,
        )
        cases.append(case)

    # CTX.addr_offset_arithmetic: address = symbol base + offset loaded from global (P1-2 on `a`)
    for type_ in ("u32", "u64"):
        add_op = "add.u32" if type_ == "u32" else "add.u64"
        reg = TYPE_REG[type_]
        coords = {"type": type_, "rank_source": "register", "rank_value": None, "addr_source": "offset_arithmetic", "context": "addr_offset_arithmetic"}
        registers = (SHARED_DECL, f".reg .{reg} %base, %addr, %dst;", ".reg .b32 %rank, %off;", ".reg .b64 %out, %poff;")
        preparation = ("ld.param.b64 %out, [p_out];", "ld.param.b64 %poff, [p_off];", "ld.global.u32 %off, [%poff];", f"mov.{type_} %base, smem;", "mov.u32 %rank, 2;")
        if type_ == "u64":
            preparation = preparation + ("cvt.u64.u32 %addr, %off;", f"{add_op} %addr, %base, %addr;")
        else:
            preparation = preparation + (f"{add_op} %addr, %base, %off;",)
        cases.append(Case("", coords, parameters=PARAMS_OUT_OFF, registers=registers, preparation=preparation, target=(_mapa_instr(type_, "%dst", "%addr", "%rank"),), observation=(_store(type_),), directives=DIRECTIVES))

    # CTX.addr_tid_derived: address offset derived from thread index arithmetic (different non-foldable flavor)
    cases.append(_context_case(
        "u32", "addr_tid_derived",
        (".reg .b32 %t0, %off;",),
        ("mov.u32 %t0, %tid.x;", "and.b32 %off, %t0, 32;", "add.u32 %addr, %addr, %off;", "mov.u32 %rank, 1;"),
        (_mapa_instr("u32", "%dst", "%addr", "%rank"),),
    ))

    # CTX.getctarank_roundtrip: rank produced by getctarank on a *different* shared::cluster
    # address, then consumed as mapa's target rank (P0-3 sequence-level combination).
    cases.append(_context_case(
        "u32", "getctarank_roundtrip",
        (".reg .b32 %narrow;", ".reg .b64 %paddr2, %addr2;"),
        ("ld.param.b64 %paddr2, [p_addr2];", "ld.global.u64 %addr2, [%paddr2];", "cvta.to.shared::cluster.u64 %addr2, %addr2;", "cvt.u32.u64 %narrow, %addr2;", "getctarank.shared::cluster.u32 %rank, %narrow;"),
        (_mapa_instr("u32", "%dst", "%addr", "%rank"),),
        parameters=(".param .u64 p_out", ".param .u64 p_addr2"),
    ))

    # CTX.guard: predicated issue. Calibrated: mapa's ALU sequence runs
    # unconditionally and the predicate is applied via SEL on the result
    # register (no @P-prefixed PRMT), because mapa has no memory side effect.
    cases.append(_context_case(
        "u32", "guarded",
        (".reg .b32 %t0;", ".reg .pred %p;"),
        ("mov.u32 %t0, %tid.x;", "setp.lt.u32 %p, %t0, 16;", "mov.u32 %rank, 1;"),
        (_mapa_instr("u32", "%dst", "%addr", "%rank", guard="@%p "),),
    ))

    # CTX.multi_target_depth_{2,4}: multiple concurrent mapa calls with distinct
    # target ranks in one kernel (P0-1 analog: own-rank S2R+LEA template is a
    # shared/CSE-able resource across calls, calibrated in `实验设计.md`).
    for depth in (2, 4):
        dsts = [f"%dst{i}" for i in range(depth)]
        ranks = [f"%rank{i}" for i in range(depth)]
        registers = (SHARED_DECL, ".reg .b32 %addr, " + ", ".join(dsts) + ", " + ", ".join(ranks) + ", %acc;", ".reg .b64 %out;")
        preparation = ["ld.param.b64 %out, [p_out];", "mov.u32 %addr, smem;"]
        preparation += [f"mov.u32 {ranks[i]}, {i};" for i in range(depth)]
        target = tuple(_mapa_instr("u32", dsts[i], "%addr", ranks[i]) for i in range(depth))
        observation = [f"mov.b32 %acc, {dsts[0]};"] + [f"xor.b32 %acc, %acc, {dsts[i]};" for i in range(1, depth)] + ["st.global.u32 [%out], %acc;"]
        coords = {"type": "u32", "rank_source": "immediate", "rank_value": None, "addr_source": "symbol_direct", "context": f"multi_target_depth_{depth}"}
        cases.append(Case("", coords, parameters=PARAMS_OUT, registers=registers, preparation=tuple(preparation), target=target, observation=tuple(observation), directives=DIRECTIVES))

    # CTX.template_wide: padded kernel parameter signature (P1-1).
    wide_params = (".param .u32 p_pad0", ".param .u64 p_out", ".param .u64 p_pad1", ".param .u32 p_pad2")
    cases.append(_context_case("u32", "template_wide", (), ("mov.u32 %rank, 1;",), (_mapa_instr("u32", "%dst", "%addr", "%rank"),), parameters=wide_params))

    # CTX.aliased_dest: d and a use the same register. Calibrated: accepted
    # (no aliasing check) -- promoted here as a positive finding per P0-2.
    coords = {"type": "u32", "rank_source": "immediate", "rank_value": 1, "addr_source": "symbol_direct", "context": "aliased_dest"}
    cases.append(Case("", coords, parameters=PARAMS_OUT, registers=(SHARED_DECL, ".reg .b32 %addr, %rank;", ".reg .b64 %out;"), preparation=("ld.param.b64 %out, [p_out];", "mov.u32 %addr, smem;", "mov.u32 %rank, 1;"), target=(_mapa_instr("u32", "%addr", "%addr", "%rank"),), observation=(_store("u32", "%addr"),), directives=DIRECTIVES))

    # CTX.no_reqnctapercluster: mapa without the `.reqnctapercluster` directive.
    # Calibrated: accepted -- ptxas does not statically require it. Promoted
    # as a positive finding per P0-2.
    coords = {"type": "u32", "rank_source": "immediate", "rank_value": 1, "addr_source": "symbol_direct", "context": "no_reqnctapercluster"}
    cases.append(Case("", coords, parameters=PARAMS_OUT, registers=(SHARED_DECL, ".reg .b32 %addr, %dst;", ".reg .b32 %rank;", ".reg .b64 %out;"), preparation=("ld.param.b64 %out, [p_out];", "mov.u32 %addr, smem;", "mov.u32 %rank, 1;"), target=(_mapa_instr("u32", "%dst", "%addr", "%rank"),), observation=(_store("u32"),), directives=()))

    # CTX.large_rank_immediate: rank far beyond any plausible cluster shape.
    # Calibrated: accepted -- no compile-time bound check on the rank
    # immediate (deferred to runtime). Promoted as a positive finding.
    cases.append(_context_case("u32", "large_rank_immediate", (), ("mov.u32 %rank, 999999;",), (_mapa_instr("u32", "%dst", "%addr", "%rank"),)))

    # CTX.consecutive_same_rank: two mapa calls with the identical rank value,
    # to observe whether ptxas CSEs the fully-identical computation.
    registers = (SHARED_DECL, ".reg .b32 %addr, %dst0, %dst1, %rank, %acc;", ".reg .b64 %out;")
    preparation = ("ld.param.b64 %out, [p_out];", "mov.u32 %addr, smem;", "mov.u32 %rank, 1;")
    target = (_mapa_instr("u32", "%dst0", "%addr", "%rank"), _mapa_instr("u32", "%dst1", "%addr", "%rank"))
    observation = ("xor.b32 %acc, %dst0, %dst1;", "st.global.u32 [%out], %acc;")
    coords = {"type": "u32", "rank_source": "immediate", "rank_value": 1, "addr_source": "symbol_direct", "context": "consecutive_same_rank"}
    cases.append(Case("", coords, parameters=PARAMS_OUT, registers=registers, preparation=preparation, target=target, observation=observation, directives=DIRECTIVES))

    return cases


def mapa_negative() -> list[Case]:
    base_registers = (SHARED_DECL, ".reg .b32 %r0, %r1;", ".reg .b32 %rank;", ".reg .b64 %out;")
    base_preparation = ("ld.param.b64 %out, [p_out];", "mov.u32 %r0, smem;", "mov.u32 %rank, 1;")

    def probe(coords: dict, target: str, reason: str, diagnostic: str, extra_registers: tuple[str, ...] = (), extra_preparation: tuple[str, ...] = ()) -> Case:
        registers = base_registers + extra_registers
        preparation = base_preparation + extra_preparation
        return Case("", coords, parameters=PARAMS_OUT, registers=registers, preparation=preparation, target=(target,), observation=(), directives=DIRECTIVES, expected="reject", reason=reason, expected_diagnostic=diagnostic)

    return [
        probe({"probe": "wrong_space_cta"}, "mapa.shared::cta.u32 %r1, %r0, %rank;", "mapa is defined only for shared::cluster, not shared::cta", "State space incorrect for instruction 'mapa', expected '::cluster'"),
        probe({"probe": "wrong_space_bare_shared"}, "mapa.shared.u32 %r1, %r0, %rank;", "bare .shared (no ::cluster) is rejected identically to ::cta", "State space incorrect for instruction 'mapa', expected '::cluster'"),
        probe({"probe": "bogus_space_global"}, "mapa.global.u32 %r1, %r0, %rank;", "a state space outside the shared family is a different diagnostic (no 'expected ::cluster' suffix)", "State space incorrect for instruction 'mapa'"),
        probe({"probe": "rank_wrong_width_u64"}, "mapa.shared::cluster.u32 %r1, %r0, %rankw;", "rank operand must be .u32 regardless of the .type modifier", "Arguments mismatch for instruction 'mapa'", extra_registers=(".reg .b64 %rankw;",), extra_preparation=("cvt.u64.u32 %rankw, %rank;",)),
        probe({"probe": "dest_width_mismatch"}, "mapa.shared::cluster.u32 %destw, %r0, %rank;", "d must match the .u32/.u64 type modifier width", "Arguments mismatch for instruction 'mapa'", extra_registers=(".reg .b64 %destw;",)),
        probe({"probe": "missing_rank_operand"}, "mapa.shared::cluster.u32 %r1, %r0;", "mapa requires exactly three operands (arity)", "Arguments mismatch for instruction 'mapa'"),
        # complement sampling outside the assumed-legal .type in {u32,u64} axis (P0-2)
        probe({"probe": "illegal_type_u16"}, "mapa.shared::cluster.u16 %r1h, %r0h, %rankh;", ".u16 is not a legal mapa type modifier", "Unexpected instruction types specified for 'mapa'", extra_registers=(".reg .b16 %r1h, %r0h, %rankh;",), extra_preparation=("cvt.u16.u32 %r0h, %r0;", "cvt.u16.u32 %rankh, %rank;")),
        probe({"probe": "rank_wrong_dtype_f32"}, "mapa.shared::cluster.u32 %r1, %r0, %rankf;", "rank declared .f32 is rejected even though it is register-width-compatible with .u32", "Arguments mismatch for instruction 'mapa'", extra_registers=(".reg .f32 %rankf;",), extra_preparation=("mov.f32 %rankf, 1.0;",)),
    ]


FACTORS = (
    {"id": "SF.type", "levels": ["u32", "u64"]},
    {"id": "SF.rank_source", "levels": ["immediate", "register"]},
    {"id": "SF.rank_value", "levels": [0, 1, 3, 7, None]},
    {"id": "SF.addr_source", "levels": ["symbol_direct", "offset_arithmetic"]},
    {"id": "CTX.context", "levels": ["baseline", "rank_indirect_producer", "addr_offset_arithmetic", "addr_tid_derived", "getctarank_roundtrip", "guarded", "multi_target_depth_2", "multi_target_depth_4", "template_wide", "aliased_dest", "no_reqnctapercluster", "large_rank_immediate", "consecutive_same_rank"]},
)

def _empty_target_allowed(coordinates: dict) -> bool:
    # Calibrated: two back-to-back mapa calls with byte-identical operands are
    # fully CSE'd by ptxas at O1-O3; the xor-based observation then folds to a
    # compile-time constant and the whole computation (including both PRMTs)
    # disappears. O0 still shows both PRMT instructions -- this is an
    # optimization-level effect, not a legality boundary. See `实验设计.md`
    # (P0-1 / redundancy-elimination finding).
    return coordinates.get("context") == "consecutive_same_rank"


SPEC = Spec(
    family="cluster",
    opcode="mapa",
    ptx_opcode="mapa",
    target_patterns=("PRMT",),
    factors=FACTORS,
    syntax_cases=mapa_cases,
    expanded_cases=mapa_expanded,
    negative_cases=mapa_negative,
    empty_target_allowed=_empty_target_allowed,
)

#!/usr/bin/env python3
"""Independent experiment definition for thread-index special registers on
Thor (`mov.u32/u64 %r, %tid.{x,y,z}` / `%ntid.{x,y,z}`).

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 (`sm_110a`):

- `%tid.{x,y,z}` always lowers to `S2R Rd, SR_TID.{X,Y,Z}` (GPR producer),
  regardless of consumer (store / address-derived / predicate / multi-use /
  shfl-broadcast) or context (`.reqntid`, divergent branch, wide template).
  It never promotes to a uniform-register (`S2UR`) producer because it is
  architecturally non-uniform per lane.
- `%ntid.{x,y,z}` always lowers to `LDC Rd, c[0x0][0x360/0x364/0x368]`
  (constant-bank producer at a fixed, ABI-reserved offset), independent of
  `.reqntid` (measured with `.reqntid 8, 4, 2`: the launch-bound hint does
  NOT fold `%ntid` into an immediate -- same LDC survives) and independent
  of user parameter-signature padding (the offset is outside user param
  space, confirmed with a 5-parameter wide signature).
- `.w`/`.a` on `%tid`/`%ntid` (the 4th vector lane) is legal PTX and folds
  to `MOV Rd, RZ` at compile time (no special-register access is issued at
  all) -- a P0-2-style calibration reversal: the obvious "diagnostic anchor"
  guess (`%tid.w` should be rejected) is wrong; `.w` is accepted and the
  rejection boundary is actually "no vector selector at all" or an unknown
  selector letter.
- `.r/.g/.b/.a` are accepted RGBA aliases for `.x/.y/.z/.w` on both
  registers (same SASS as the XYZW spelling).
- `mov.v4.u32 {...}, %tid` / `%ntid` is legal and lowers to per-component
  `S2R`/`LDC` with dead-component elimination (reading only `.x` from the
  v4 form emits exactly the same single instruction as `mov.u32 %r,%tid.x`).

See `../../实验设计.md` for the full register-to-producer table (47 special
registers) and the `%tid`/`%ctaid` manipulation-check writeup this suite's
`context` axis is drawn from.
"""

from suite_runtime import Case, Spec

PARAMS = (".param .u64 p_base", ".param .u64 p_out")

TID_TARGET_PATTERNS = ("SR_TID.X", "SR_TID.Y", "SR_TID.Z")
NTID_TARGET_PATTERNS = ("c[0x0][0x360]", "c[0x0][0x364]", "c[0x0][0x368]")

DIM_OFFSET = {"x": "0x360", "y": "0x364", "z": "0x368"}


def _sreg(kind: str, dim: str) -> str:
    return f"%{kind}.{dim}"


def _base_registers(extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    return (".reg .b32 %r0, %r1, %r2;", ".reg .b64 %basep, %outp, %rd0, %addr;", ".reg .u32 %v;", ".reg .pred %p;", *extra)


def _coords(kind: str, dim: str, consumer: str, context: str = "baseline") -> dict:
    return {"kind": kind, "dim": dim, "consumer": consumer, "context": context}


def _consumer_body(kind: str, dim: str, consumer: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (preparation, observation) for a given consumer shape. The
    target read itself is always exactly one `mov` unless overridden by the
    caller (double_read builds its own target)."""
    if consumer == "store":
        return (("ld.param.u64 %outp, [p_out];",), ("st.global.u32 [%outp], %r0;",))
    if consumer == "address":
        return (
            ("ld.param.u64 %basep, [p_base];", "ld.param.u64 %outp, [p_out];"),
            ("mul.wide.u32 %rd0, %r0, 4;", "add.u64 %addr, %basep, %rd0;", "ld.global.u32 %v, [%addr];", "st.global.u32 [%outp], %v;"),
        )
    if consumer == "predicate":
        return (
            ("ld.param.u64 %outp, [p_out];",),
            ("setp.lt.u32 %p, %r0, 16;", "mov.u32 %r1, 7;", "@%p st.global.u32 [%outp], %r1;", "@!%p st.global.u32 [%outp], %r0;"),
        )
    if consumer == "multi_use":
        return (
            ("ld.param.u64 %outp, [p_out];",),
            ("add.u32 %r1, %r0, 1;", "xor.b32 %r2, %r0, %r1;", "st.global.u32 [%outp], %r2;"),
        )
    raise ValueError(consumer)


def _case(kind: str, dim: str, consumer: str, context: str = "baseline", directives: tuple[str, ...] = (), parameters: tuple[str, ...] = PARAMS) -> Case:
    sreg = _sreg(kind, dim)
    prep, obs = _consumer_body(kind, dim, consumer)
    return Case(
        "",
        _coords(kind, dim, consumer, context),
        parameters=parameters,
        registers=_base_registers(),
        preparation=prep,
        target=(f"mov.u32 %r0, {sreg};",),
        observation=obs,
        directives=directives,
    )


def thread_index_cases() -> list[Case]:
    cases = []
    for kind in ("tid", "ntid"):
        for dim in ("x", "y", "z"):
            for consumer in ("store", "address", "predicate", "multi_use"):
                cases.append(_case(kind, dim, consumer))
    return cases


def thread_index_expanded() -> list[Case]:
    cases = thread_index_cases()

    # CTX.reqntid_present -- P1-1 "hidden global variable" axis: does the
    # launch-bound hint fold %ntid into an immediate? Calibrated: no.
    for kind in ("tid", "ntid"):
        for dim in ("x", "y", "z"):
            cases.append(_case(kind, dim, "store", context="reqntid_present", directives=(".reqntid 8, 4, 2",)))

    # CTX.double_read -- two independent PTX reads of the same sreg; does
    # ptxas CSE the second S2R/LDC or reissue it?
    for kind in ("tid", "ntid"):
        for dim in ("x", "y", "z"):
            sreg = _sreg(kind, dim)
            cases.append(Case(
                "",
                _coords(kind, dim, "store", context="double_read"),
                parameters=PARAMS,
                registers=_base_registers(),
                preparation=("ld.param.u64 %outp, [p_out];",),
                target=(f"mov.u32 %r0, {sreg};", f"mov.u32 %r1, {sreg};"),
                observation=("add.u32 %r2, %r0, %r1;", "st.global.u32 [%outp], %r2;"),
            ))

    # CTX.template_wide -- padded/shuffled kernel signature (P1-1 template
    # axis); calibrated: the sreg constant-bank table offset (%ntid) sits
    # outside user parameter space and is unaffected by padding.
    wide_params = (".param .u32 p_pad0", ".param .u64 p_base", ".param .u64 p_pad1", ".param .u64 p_out", ".param .u32 p_pad2")
    for kind in ("tid", "ntid"):
        cases.append(_case(kind, "x", "store", context="template_wide", parameters=wide_params))

    # CTX.shfl_broadcast -- uniformity-manipulation axis (task-mandated):
    # consume the read via shfl.sync.idx from lane 0 instead of a direct
    # store. Calibrated finding: %tid.x keeps its S2R AND the SHFL.IDX
    # persists (non-uniform, cannot be proven constant across the warp);
    # %ntid.x keeps its LDC but the SHFL.IDX is eliminated entirely
    # (provably uniform across the warp, shuffling it from lane 0 is a
    # no-op ptxas removes) -- same consumer instruction, opposite fate.
    for kind in ("tid", "ntid"):
        sreg = _sreg(kind, "x")
        cases.append(Case(
            "",
            _coords(kind, "x", "shfl_broadcast", context="shfl_broadcast"),
            parameters=PARAMS,
            registers=_base_registers((".reg .b32 %r3;",)),
            preparation=("ld.param.u64 %outp, [p_out];",),
            target=(f"mov.u32 %r0, {sreg};",),
            observation=("shfl.sync.idx.b32 %r3, %r0, 0, 31, -1;", "st.global.u32 [%outp], %r3;"),
        ))

    # CTX.divergent_branch -- uniformity-manipulation axis, scattered-
    # consumption variant: %ntid.x (provably CTA-uniform) consumed inside a
    # per-thread-divergent branch. The branch condition deliberately uses
    # %laneid (not %tid.x) so the branch-generating instruction cannot be
    # mistaken by target_patterns for a second occurrence of the %tid.x
    # target (SR_TID.X would otherwise also match an unrelated
    # observation-side S2R and contaminate the attribution -- exactly the
    # over-matching pitfall the family guide warns about). Calibrated
    # finding: the producer mechanism (LDC constant-bank) is unchanged;
    # ptxas converts the branch to predicated execution around it, it does
    # not touch the sreg lowering itself. %tid.x (itself the branch
    # condition) is the "fully scattered" contrast case below.
    cases.append(Case(
        "",
        _coords("ntid", "x", "divergent_branch", context="divergent_branch"),
        parameters=PARAMS,
        registers=_base_registers((".reg .b32 %tt;",)),
        preparation=("ld.param.u64 %outp, [p_out];",),
        target=("mov.u32 %r0, %ntid.x;",),
        observation=("mov.u32 %tt, %laneid;", "setp.lt.u32 %p, %tt, 16;", "@%p bra L_then_ntid;", "mov.u32 %r1, 0;", "bra L_end_ntid;", "L_then_ntid:", "add.u32 %r1, %r0, 1;", "L_end_ntid:", "st.global.u32 [%outp], %r1;"),
    ))
    cases.append(Case(
        "",
        _coords("tid", "x", "divergent_branch", context="divergent_branch"),
        parameters=PARAMS,
        registers=_base_registers(),
        preparation=("ld.param.u64 %outp, [p_out];",),
        target=("mov.u32 %r0, %tid.x;",),
        observation=("setp.lt.u32 %p, %r0, 16;", "@%p bra L_then_tid;", "mov.u32 %r1, 0;", "bra L_end_tid;", "L_then_tid:", "add.u32 %r1, %r0, 1;", "L_end_tid:", "st.global.u32 [%outp], %r1;"),
    ))

    # CTX.vector_read_v4 -- structural class check: mov.v4.u32 reading the
    # whole vector register at once, all four components consumed via a
    # reduction xor. Calibrated: lowers to per-component S2R/LDC (x,y,z)
    # plus a compile-time RZ fold for the architectural w-lane -- same
    # producer mechanism as the scalar form, no fourth instruction.
    for kind in ("tid", "ntid"):
        cases.append(Case(
            "",
            _coords(kind, "xyzw", "vector_read", context="vector_read_v4"),
            parameters=PARAMS,
            registers=(".reg .b32 %r0, %r1, %r2, %r3, %r4;", ".reg .b64 %outp;"),
            preparation=("ld.param.u64 %outp, [p_out];",),
            target=(f"mov.v4.u32 {{%r0, %r1, %r2, %r3}}, %{kind};",),
            observation=("xor.b32 %r4, %r0, %r1;", "xor.b32 %r4, %r4, %r2;", "xor.b32 %r4, %r4, %r3;", "st.global.u32 [%outp], %r4;"),
        ))

    # CTX.spelling_rgba -- accepted alternate spelling: r/g/b/a aliases for
    # x/y/z/w (calibrated legal, identical SASS to the xyzw spelling).
    cases.append(Case(
        "",
        _coords("tid", "x", "store", context="spelling_rgba"),
        parameters=PARAMS,
        registers=_base_registers(),
        preparation=("ld.param.u64 %outp, [p_out];",),
        target=("mov.u32 %r0, %tid.r;",),
        observation=("st.global.u32 [%outp], %r0;",),
    ))
    cases.append(Case(
        "",
        _coords("ntid", "y", "store", context="spelling_rgba"),
        parameters=PARAMS,
        registers=_base_registers(),
        preparation=("ld.param.u64 %outp, [p_out];",),
        target=("mov.u32 %r0, %ntid.g;",),
        observation=("st.global.u32 [%outp], %r0;",),
    ))

    return cases


def thread_index_negative() -> list[Case]:
    def probe(coords: dict, target: str, reason: str, diagnostic: str) -> Case:
        return Case(
            "",
            coords,
            parameters=PARAMS,
            registers=_base_registers(),
            preparation=("ld.param.u64 %outp, [p_out];",),
            target=(target,),
            observation=(),
            expected="reject",
            reason=reason,
            expected_diagnostic=diagnostic,
        )

    return [
        probe({"probe": "tid_no_component"}, "mov.u32 %r0, %tid;", "tid is a v4 register; a component selector is mandatory for a scalar mov", "Argument vector size mismatch"),
        probe({"probe": "ntid_no_component"}, "mov.u32 %r0, %ntid;", "complement: same vector-arity constraint holds for ntid", "Argument vector size mismatch"),
        probe({"probe": "tid_v2_mismatch"}, "mov.v2.u32 {%r0, %r1}, %tid;", "tid is v4-shaped; a v2 vector mov cannot bind to it", "Argument vector size mismatch"),
        probe({"probe": "tid_bad_selector"}, "mov.u32 %r0, %tid.q;", "q is not a defined vector selector (only x/y/z/w and r/g/b/a)", "Unknown vector selector"),
        probe({"probe": "ntid_bad_selector"}, "mov.u32 %r0, %ntid.q;", "complement: unknown-selector rejection generalizes to ntid", "Unknown vector selector"),
        probe({"probe": "tid_width_mismatch_u64"}, "mov.u64 %r0, %tid.x;", "tid.x is .u32; a 64-bit mov cannot bind to a 32-bit special register", "Arguments mismatch for instruction 'mov'"),
        probe({"probe": "ntid_width_mismatch_u64"}, "mov.u64 %r0, %ntid.x;", "complement: same width constraint holds for ntid", "Arguments mismatch for instruction 'mov'"),
        probe({"probe": "tid_width_mismatch_s64"}, "mov.s64 %r0, %tid.x;", "complement: width mismatch is about size, not signedness -- s64 rejected the same as u64", "Arguments mismatch for instruction 'mov'"),
        probe({"probe": "unknown_sreg"}, "mov.u32 %r0, %tid_bogus;", "not a special register or declared identifier", "Unknown symbol"),
    ]


FACTORS = (
    {"id": "SF.kind", "levels": ["tid", "ntid"]},
    {"id": "SF.dim", "levels": ["x", "y", "z"]},
    {"id": "SF.consumer", "levels": ["store", "address", "predicate", "multi_use"]},
    {"id": "CTX.context", "levels": ["baseline", "reqntid_present", "double_read", "template_wide", "shfl_broadcast", "divergent_branch", "vector_read_v4", "spelling_rgba"]},
)

SPEC = Spec(
    family="sreg",
    opcode="thread_index",
    ptx_opcode="mov",
    target_patterns=TID_TARGET_PATTERNS + NTID_TARGET_PATTERNS,
    factors=FACTORS,
    syntax_cases=thread_index_cases,
    expanded_cases=thread_index_expanded,
    negative_cases=thread_index_negative,
    empty_target_allowed=lambda _coordinates: False,
)

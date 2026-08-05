#!/usr/bin/env python3
"""Independent experiment definition for ld.global on Thor (sm_110a, PTX 9.0).

Every legal-matrix entry below was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 in scratchpad probes before being frozen here (guide step
1: "先校准, 后设计"). Headline calibration facts baked into this spec:

- width x cache-op (weak form): .ca -> LDG.E...STRONG.SM, .cg -> STRONG.GPU,
  .cv -> STRONG.SYS, .cs -> EF, .lu -> LU, no cop -> plain LDG.E[.width].
  These are the exact same STRONG.SM/STRONG.GPU/STRONG.SYS bit patterns
  produced by relaxed/acquire + cta/gpu-or-cluster/sys and by `.volatile`
  (STRONG.SYS). Verified bit-identical at the full two-word encoding level,
  not just the mnemonic text -- weak+cache-op and explicit-scope ordering
  share one encoding family on this target. relaxed and acquire are
  bit-identical to each other in isolation (no MEMBAR is inserted either);
  the ordering distinction is not visible in a lone load's SASS.
- ld.global.nc: legal, lowers to LDG.E.CONSTANT irrespective of a stacked
  .ca/.cg (all three collapse to one bit pattern); nc rejects relaxed/
  acquire/mmio/volatile ("cannot be combined with modifier '.nc'").
- generic (state-space-free) ld/st against a cvta.global-derived pointer
  lowers to a *different* mnemonic family, LD.E/ST.E, not LDG.E/STG.E --
  and with no visible runtime space-check branch sequence.
- register+offset folds into the LDG/STG own operand only at O1-O3, and
  only within the signed 24-bit field [-0x800000, 0x7fffff]; O0 always
  materializes the address with IADD3 first. Beyond the boundary the
  compiler splits the constant via an extra (U)IADD3 on the base plus the
  opposite-sign boundary immediate.
- scalar .b128 is LEGAL on ld/st.global (STG.E.128, same width class as
  v4.b32/v2.b64) -- this falsifies the naive assumption that a scalar
  128-bit width is illegal; the genuinely illegal vector width is .v3
  ("Illegal vector size: 3"), used as the negative probe instead.
- ldu.global.{b8,b16,b32,b64,v2.b32,v4.b32} all compile and lower to plain
  LDG.E[.width] -- bit-identical encoding to ld.global at matching width.
  No distinct uniform-datapath SASS opcode was observed for ldu.

See PTX_SASS_mapping/07_lsu/实验设计.md for the full calibration table and
scratchpad probe inventory this spec was derived from.
"""

from suite_runtime import Case, Spec

PARAMS = (".param .u64 p_in", ".param .u64 p_out")

# ---------------------------------------------------------------------------
# width -> (dest register declaration, dest operand text, storable PTX type)
# ---------------------------------------------------------------------------


def _dst(width: str):
    if width == "b8":
        return (".reg .b16 %d0;",), "%d0"
    if width == "b16":
        return (".reg .b16 %d0;",), "%d0"
    if width == "b32":
        return (".reg .b32 %d0;",), "%d0"
    if width == "b64":
        return (".reg .b64 %d0;",), "%d0"
    if width == "b128":
        return (".reg .b128 %d0;",), "%d0"
    if width == "v2.b32":
        return (".reg .b32 %d0, %d1;",), "{%d0, %d1}"
    if width == "v4.b32":
        return (".reg .b32 %d0, %d1, %d2, %d3;",), "{%d0, %d1, %d2, %d3}"
    raise ValueError(width)


def _store_line(width: str, out_reg: str = "%out") -> str:
    _, dst = _dst(width)
    return f"st.global.{width} [{out_reg}], {dst};"


# ---------------------------------------------------------------------------
# form -> ld.global mnemonic prefix (everything before the width token)
# ---------------------------------------------------------------------------

WEAK_COP = {"none": "", "ca": ".ca", "cg": ".cg", "cs": ".cs", "lu": ".lu", "cv": ".cv"}
NC_COP = {"none": "", "ca": ".ca", "cg": ".cg"}


def _mnemonic(form: str) -> str:
    if form == "volatile":
        return "ld.volatile.global"
    if form.startswith("weak_"):
        return f"ld.global{WEAK_COP[form[5:]]}"
    if form.startswith("nc_"):
        return f"ld.global.nc{NC_COP[form[3:]]}"
    if form.startswith("relaxed_") or form.startswith("acquire_"):
        sem, scope = form.split("_", 1)
        return f"ld.global.{sem}.{scope}"
    raise ValueError(form)


def _ld_line(width: str, form: str, addr: str, guard: str = "") -> str:
    _, dst = _dst(width)
    vec = ""
    base_width = width
    if width in ("v2.b32", "v4.b32"):
        vec, base_width = width.split(".")
        vec = f".{vec}"
    return f"{guard}{_mnemonic(form)}{vec}.{base_width} {dst}, [{addr}];"


def _addr(offset=None, base: str = "%in") -> str:
    return f"[{base}]" if offset is None else f"[{base}+{offset}]"


def _case(width: str, form: str, address_form: str = "reg", context: str = "baseline",
          addr_offset=None, guard: str = "", extra_regs=(), extra_prep=(),
          extra_params: tuple[str, ...] = PARAMS, target_override: str | None = None) -> Case:
    decl, _ = _dst(width)
    coords = {"width": width, "form": form, "address_form": address_form, "context": context}
    addr_text = f"%in+{addr_offset}" if addr_offset is not None else "%in"
    line = target_override or _ld_line(width, form, addr_text, guard=guard)
    registers = (".reg .b64 %in, %out;", *decl, *extra_regs)
    preparation = ("ld.param.b64 %in, [p_in];", "ld.param.b64 %out, [p_out];", *extra_prep)
    return Case(
        "", coords,
        parameters=extra_params,
        registers=registers,
        preparation=preparation,
        target=(line,),
        observation=(_store_line(width),),
    )


# ---------------------------------------------------------------------------
# syntax_cases: the calibrated legal matrix
# ---------------------------------------------------------------------------

WIDTHS = ("b8", "b16", "b32", "b64", "v2.b32", "v4.b32")
COPS = ("none", "ca", "cg", "cs", "lu", "cv")


def ld_global_cases() -> list[Case]:
    cases: list[Case] = []

    # A. width x cache-op, full cross (weak form) -- the core calibration table.
    for width in WIDTHS:
        for cop in COPS:
            cases.append(_case(width, f"weak_{cop}"))

    # B. sem x scope at fixed width b32 -- relaxed/acquire x cta/cluster/gpu/sys.
    for sem in ("relaxed", "acquire"):
        for scope in ("cta", "cluster", "gpu", "sys"):
            cases.append(_case("b32", f"{sem}_{scope}"))

    # C. sem(relaxed.gpu/acquire.gpu) x width pairwise sample beyond b32/b64
    #    (b32/b64 already exercised by axis B and the volatile axis below).
    cases.append(_case("b8", "relaxed_gpu"))
    cases.append(_case("b16", "acquire_gpu"))
    cases.append(_case("v2.b32", "relaxed_gpu"))
    cases.append(_case("v4.b32", "acquire_gpu"))
    cases.append(_case("b64", "relaxed_gpu"))

    # D. volatile x width, full (small axis, all widths legal).
    for width in WIDTHS:
        cases.append(_case(width, "volatile"))

    # E. explicit .weak spelling equivalence check (documented as == weak_none).
    cases.append(_case("b32", "weak_none", context="weak_explicit_spelling",
                        target_override="ld.weak.global.b32 %d0, [%in];"))

    # F. ld.global.nc forms: a few widths x {none, ca, cg} -- ca/cg collapse
    #    onto the same LDG.E.CONSTANT bit pattern as plain nc (calibrated).
    for width in ("b32", "b64", "v2.b32"):
        cases.append(_case(width, "nc_none"))
    cases.append(_case("b32", "nc_ca"))
    cases.append(_case("b32", "nc_cg"))

    # G. address-form axis at fixed width b32: register, +/- small offset,
    #    +/- boundary offset around the signed 24-bit LDG/STG immediate
    #    field [-0x800000, 0x7fffff], and a named-symbol form.
    cases.append(_case("b32", "weak_none", address_form="reg_pos_small", addr_offset=64,
                        context="address_form"))
    cases.append(_case("b32", "weak_none", address_form="reg_neg_small", addr_offset=-64,
                        context="address_form"))
    cases.append(_case("b32", "weak_none", address_form="reg_pos_boundary", addr_offset=8388607,
                        context="address_form"))
    cases.append(_case("b32", "weak_none", address_form="reg_pos_beyond", addr_offset=8388608,
                        context="address_form"))
    cases.append(_case("b32", "weak_none", address_form="reg_neg_boundary", addr_offset=-8388608,
                        context="address_form"))
    cases.append(_case("b32", "weak_none", address_form="reg_neg_beyond", addr_offset=-8388609,
                        context="address_form"))
    cases.append(Case(
        "", {"width": "b32", "form": "weak_none", "address_form": "named_symbol", "context": "address_form"},
        parameters=PARAMS,
        declarations=(".global .align 4 .b32 lsu_probe_gsym[4] = {1, 2, 3, 4};",),
        registers=(".reg .b64 %in, %out;", ".reg .b32 %d0;"),
        preparation=("ld.param.b64 %in, [p_in];", "ld.param.b64 %out, [p_out];"),
        target=("ld.global.b32 %d0, [lsu_probe_gsym];",),
        observation=(_store_line("b32"),),
    ))

    # H. extra width point: scalar .b128 (calibrated legal, aliases v4.b32
    #    class). Not part of the task's core width axis, kept as a
    #    documented falsification of the "b128 scalar is illegal" guess.
    cases.append(_case("b128", "weak_none", context="extra_width_b128"))
    cases.append(_case("b128", "weak_cg", context="extra_width_b128"))

    return cases


# ---------------------------------------------------------------------------
# expanded_cases: P0-1/P0-3/P1-1/P1-2 context axes
# ---------------------------------------------------------------------------


def ld_global_expanded() -> list[Case]:
    cases = ld_global_cases()

    # CTX.pointer_to_pointer (P1-2): address itself is loaded from memory,
    # not folded from a parameter -- "指针的指针".
    cases.append(Case(
        "", {"width": "b32", "form": "weak_none", "address_form": "reg", "context": "pointer_to_pointer"},
        parameters=(".param .u64 p_pp", ".param .u64 p_out"),
        registers=(".reg .b64 %pp, %out, %p;", ".reg .b32 %d0;"),
        preparation=("ld.param.b64 %pp, [p_pp];", "ld.param.b64 %out, [p_out];", "ld.global.u64 %p, [%pp];"),
        target=("ld.global.b32 %d0, [%p];",),
        observation=(_store_line("b32"),),
    ))

    # CTX.same_address_double_load: two loads from the identical address
    # with different cache-op forms so both survive as distinct instructions
    # (P0-3: at-least-double modifier combination in one sequence).
    cases.append(Case(
        "", {"width": "b32", "form": "weak_none", "address_form": "reg", "context": "same_address_double_load"},
        parameters=PARAMS,
        registers=(".reg .b64 %in, %out;", ".reg .b32 %d0, %d1, %s;"),
        preparation=("ld.param.b64 %in, [p_in];", "ld.param.b64 %out, [p_out];"),
        target=("ld.global.b32 %d0, [%in];", "ld.global.cg.b32 %d1, [%in];"),
        observation=("add.u32 %s, %d0, %d1;", "st.global.b32 [%out], %s;"),
    ))

    # CTX.adjacent_alias_ld_st: store through one pointer, then load through
    # a second, independently-derived pointer the compiler cannot prove
    # disjoint from the first ("可能别名" axis).
    cases.append(Case(
        "", {"width": "b32", "form": "weak_none", "address_form": "reg", "context": "adjacent_may_alias_ld_st"},
        parameters=(".param .u64 p_in", ".param .u64 p_in2", ".param .u64 p_out"),
        registers=(".reg .b64 %in, %in2, %out;", ".reg .b32 %d0, %s;"),
        preparation=("ld.param.b64 %in, [p_in];", "ld.param.b64 %in2, [p_in2];", "ld.param.b64 %out, [p_out];",
                      "mov.u32 %s, 7;", "st.global.b32 [%in], %s;"),
        target=("ld.global.b32 %d0, [%in2];",),
        observation=(_store_line("b32"),),
    ))

    # CTX.guard: predicated issue (uniform-looking predicate derived from
    # tid, not the special register itself used as a user name).
    cases.append(Case(
        "", {"width": "b32", "form": "weak_none", "address_form": "reg", "context": "guarded"},
        parameters=PARAMS,
        registers=(".reg .b64 %in, %out;", ".reg .b32 %d0, %t0;", ".reg .pred %p;"),
        preparation=("ld.param.b64 %in, [p_in];", "ld.param.b64 %out, [p_out];",
                      "mov.u32 %t0, %tid.x;", "setp.lt.u32 %p, %t0, 16;", "mov.u32 %d0, 0;"),
        target=("@%p ld.global.b32 %d0, [%in];",),
        observation=(_store_line("b32"),),
    ))

    # CTX.template_wide (P1-1): padded / reordered parameter signature.
    wide_params = (".param .u32 p_pad0", ".param .u64 p_in", ".param .u64 p_pad1",
                    ".param .u64 p_out", ".param .u32 p_pad2")
    cases.append(_case("b32", "weak_none", context="template_wide", extra_params=wide_params))

    # CTX.inflight_depth_{2,4} (P0-1): several in-flight loads before the
    # first is consumed -- scoreboard control-word axis.
    for depth in (2, 4):
        offsets = [4 * i for i in range(depth)]
        target_lines = tuple(f"ld.global.b32 %d{i}, [%in+{off}];" for i, off in enumerate(offsets))
        regs = ".reg .b32 " + ", ".join(f"%d{i}" for i in range(depth)) + ", %s;"
        adds = tuple(f"add.u32 %s, %s, %d{i};" if i else f"mov.u32 %s, %d{i};" for i, _ in enumerate(offsets))
        cases.append(Case(
            "", {"width": "b32", "form": "weak_none", "address_form": "reg", "context": f"inflight_depth_{depth}"},
            parameters=PARAMS,
            registers=(".reg .b64 %in, %out;", regs),
            preparation=("ld.param.b64 %in, [p_in];", "ld.param.b64 %out, [p_out];"),
            target=target_lines,
            observation=(*adds, "st.global.b32 [%out], %s;"),
        ))

    # CTX.scope_plus_inflight: combine an already-calibrated double modifier
    # (STRONG.SYS via acquire.sys) with an in-flight depth of 2 (P0-3:
    # "至少覆盖已校准的双修饰符组合" applied at sequence level).
    cases.append(Case(
        "", {"width": "b32", "form": "acquire_sys", "address_form": "reg", "context": "scope_plus_inflight_2"},
        parameters=PARAMS,
        registers=(".reg .b64 %in, %out;", ".reg .b32 %d0, %d1, %s;"),
        preparation=("ld.param.b64 %in, [p_in];", "ld.param.b64 %out, [p_out];"),
        target=("ld.global.acquire.sys.b32 %d0, [%in];", "ld.global.acquire.sys.b32 %d1, [%in+4];"),
        observation=("add.u32 %s, %d0, %d1;", "st.global.b32 [%out], %s;"),
    ))

    # CTX.consume_distance_far: widen the gap between issue and consumption
    # with filler ALU ops (mirrors the TMA wait_distance axis) to see
    # whether the scoreboard-wait control word shifts with distance.
    filler = tuple(f"add.u32 %f, %f, {i};" for i in range(1, 9))
    cases.append(Case(
        "", {"width": "b32", "form": "weak_none", "address_form": "reg", "context": "consume_distance_far"},
        parameters=PARAMS,
        registers=(".reg .b64 %in, %out;", ".reg .b32 %d0, %f;"),
        preparation=("ld.param.b64 %in, [p_in];", "ld.param.b64 %out, [p_out];", "mov.u32 %f, 0;"),
        target=("ld.global.b32 %d0, [%in];",),
        observation=(*filler, "add.u32 %f, %f, %d0;", "st.global.b32 [%out], %f;"),
    ))

    return cases


# ---------------------------------------------------------------------------
# negative_cases: calibrated diagnostics + complement sampling (P0-2)
# ---------------------------------------------------------------------------


def _neg(coords: dict, target: str, reason: str, diagnostic: str) -> Case:
    return Case(
        "", coords,
        parameters=PARAMS,
        registers=(".reg .b64 %in, %out;", ".reg .b32 %d0, %d1, %d2;"),
        preparation=("ld.param.b64 %in, [p_in];", "ld.param.b64 %out, [p_out];"),
        target=(target,),
        observation=(),
        expected="reject",
        reason=reason,
        expected_diagnostic=diagnostic,
    )


def ld_global_negative() -> list[Case]:
    return [
        _neg({"probe": "cop_plus_relaxed"}, "ld.global.ca.relaxed.gpu.b32 %d0, [%in];",
             "cache-op and explicit ordering scope are mutually exclusive modifier groups",
             "Modifier '.relaxed' cannot be combined with modifier '.ca'"),
        _neg({"probe": "volatile_plus_cop"}, "ld.volatile.global.ca.b32 %d0, [%in];",
             "volatile is its own form and cannot carry a cache-op", "Modifier '.volatile' cannot be combined with modifier '.ca'"),
        _neg({"probe": "sem_missing_scope"}, "ld.global.relaxed.b32 %d0, [%in];",
             "relaxed/acquire require an explicit scope qualifier", "Modifier '.relaxed' requires scope with 'ld' instruction"),
        _neg({"probe": "store_cop_on_load"}, "ld.global.wb.b32 %d0, [%in];",
             ".wb/.wt are store-direction cache-ops, illegal on ld", "Illegal modifier '.wb' for instruction 'ld'"),
        _neg({"probe": "duplicate_acquire"}, "ld.weak.acquire.gpu.global.b32 %d0, [%in];",
             ".weak and .acquire cannot both tag the same load", "Duplicate .acquire modifier"),
        _neg({"probe": "nc_plus_relaxed"}, "ld.global.nc.relaxed.gpu.b32 %d0, [%in];",
             "nc (non-coherent/read-only) path has no ordering-scope form", "Modifier '.relaxed' cannot be combined with modifier '.nc'"),
        _neg({"probe": "multiple_cache_ops"}, "ld.global.cv.lu.b32 %d0, [%in];",
             "at most one cache-op modifier may be present", "Multiple cache operation modifiers specified"),
        _neg({"probe": "sem_scope_plus_cop"}, "ld.global.acquire.gpu.ca.b32 %d0, [%in];",
             "explicit-scope ordering and cache-op remain mutually exclusive with scope present", "Modifier '.acquire' cannot be combined with modifier '.ca'"),
        # complement sampling outside the assumed-legal surface (P0-2)
        _neg({"probe": "vector_v3"}, "ld.global.v3.b32 {%d0, %d1, %d2}, [%in];",
             "PTX only defines v2/v4 vector widths, not v3", "Illegal vector size: 3"),
        _neg({"probe": "mmio_missing_scope"}, "ld.global.relaxed.mmio.b32 %d0, [%in];",
             "an .mmio modifier exists in this PTX ISA and independently requires scope -- "
             "assumed-legal surface omitted it, boundary probe finds the real constraint", "Modifier '.mmio' requires scope with 'ld' instruction"),
    ]


FACTORS = (
    {"id": "SF.width", "levels": list(WIDTHS) + ["b128"]},
    {"id": "SF.cache_op", "levels": list(COPS)},
    {"id": "SF.sem", "levels": ["weak", "relaxed", "acquire", "volatile", "nc"]},
    {"id": "SF.scope", "levels": ["cta", "cluster", "gpu", "sys"]},
    {"id": "SF.address_form", "levels": ["reg", "reg_pos_small", "reg_neg_small", "reg_pos_boundary",
                                          "reg_pos_beyond", "reg_neg_boundary", "reg_neg_beyond", "named_symbol"]},
    {"id": "CTX.context", "levels": ["baseline", "weak_explicit_spelling", "address_form", "extra_width_b128",
                                      "pointer_to_pointer", "same_address_double_load", "adjacent_may_alias_ld_st",
                                      "guarded", "template_wide", "inflight_depth_2", "inflight_depth_4",
                                      "scope_plus_inflight_2", "consume_distance_far"]},
)

SPEC = Spec(
    family="lsu",
    opcode="ld_global",
    ptx_opcode="ld.global",
    target_patterns=("LDG",),
    factors=FACTORS,
    syntax_cases=ld_global_cases,
    expanded_cases=ld_global_expanded,
    negative_cases=ld_global_negative,
    empty_target_allowed=lambda _coordinates: False,
)

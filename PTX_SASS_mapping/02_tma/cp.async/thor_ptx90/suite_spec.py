#!/usr/bin/env python3
"""Independent experiment definition for classic cp.async on Thor.

Calibrated against ptxas V13.0.88 / nvdisasm V13.0.85 (`sm_110a`): the copy
maps 1:1 to LDGSTS.E with size suffixes {none,.64,.128}, `.cg` adds .BYPASS,
src-size adds .ZFILL (src-size 0 folds to the ignore-src operand form `, !PT`),
`.L2::{64,128,256}B` adds .LTC{64,128,256}B, and `.L2::cache_hint` switches the
operand form to `desc[UR]` with the shared destination moving to a UR. The
commit/wait protocol (LDGDEPBAR / DEPBAR.LE SB0) is exercised here only as
observation context; it is owned by the cp.async.commit_group and
cp.async.wait_group directories.
"""

from suite_runtime import Case, Spec

PARAMS = (".param .u64 p_g", ".param .u64 p_out")
DIRECTIVES = (".reqntid 128",)

BASE_OBSERVATION = (
    "cp.async.commit_group;",
    "cp.async.wait_group 0;",
    "bar.sync 0;",
    "ld.shared.b32 %v, [%saddr];",
    "st.global.b32 [%out], %v;",
)


def _registers(cache_hint: bool = False, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    regs = [
        ".shared .align 16 .b8 smem[256];",
        ".reg .b32 %saddr, %v;",
        ".reg .b64 %g, %out;",
    ]
    if cache_hint:
        regs.append(".reg .b64 %pol;")
    regs.extend(extra)
    return tuple(regs)


def _preparation(cache_hint: bool = False, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    prep = [
        "ld.param.b64 %g, [p_g];",
        "ld.param.b64 %out, [p_out];",
        "mov.u32 %saddr, smem;",
    ]
    if cache_hint:
        prep.append("createpolicy.fractional.L2::evict_last.b64 %pol, 1.0;")
    prep.extend(extra)
    return tuple(prep)


def _instr(cache_op: str, size: int, src_size: int | None = None, ignore_src: str = "", prefetch: str = "", cache_hint: bool = False, space: str = "shared", guard: str = "") -> str:
    mods = f"{'.L2::cache_hint' if cache_hint else ''}{'.' + prefetch if prefetch else ''}"
    tail = ""
    if src_size is not None:
        tail += f", {src_size}"
    if ignore_src:
        tail += f", {ignore_src}"
    if cache_hint:
        tail += ", %pol"
    return f"{guard}cp.async.{cache_op}.{space}.global{mods} [%saddr], [%g], {size}{tail};"


def _case(coords: dict, target: tuple[str, ...], cache_hint: bool = False, registers_extra: tuple[str, ...] = (), preparation_extra: tuple[str, ...] = (), observation: tuple[str, ...] = BASE_OBSERVATION, parameters: tuple[str, ...] = PARAMS) -> Case:
    return Case("", coords, parameters=parameters, registers=_registers(cache_hint, registers_extra), preparation=_preparation(cache_hint, preparation_extra), target=target, observation=observation, directives=DIRECTIVES)


PRED_SETUP = ((".reg .b32 %t0;", ".reg .pred %p;"), ("mov.u32 %t0, %tid.x;", "setp.lt.u32 %p, %t0, 16;"))


def cp_async_cases() -> list[Case]:
    cases = []
    # cache-op x cp-size legal surface: ca in {4,8,16}, cg in {16}
    for cache_op, size in (("ca", 4), ("ca", 8), ("ca", 16), ("cg", 16)):
        cases.append(_case({"cache_op": cache_op, "size": size, "src_size": None, "ignore_src": False, "prefetch": "none", "cache_hint": False, "impl": "canonical", "context": "baseline"}, (_instr(cache_op, size),)))
    # explicit shared::cta spelling, same semantic form as ca-4 canonical
    cases.append(_case({"cache_op": "ca", "size": 4, "src_size": None, "ignore_src": False, "prefetch": "none", "cache_hint": False, "impl": "shared_cta_spelling", "context": "baseline"}, (_instr("ca", 4, space="shared::cta"),)))
    # src-size (zero-fill) axis; src-size 0 folds to the ignore-src operand form
    for cache_op, size, src in (("ca", 16, 8), ("ca", 16, 4), ("ca", 16, 12), ("ca", 8, 4), ("ca", 16, 0)):
        cases.append(_case({"cache_op": cache_op, "size": size, "src_size": src, "ignore_src": False, "prefetch": "none", "cache_hint": False, "impl": "canonical", "context": "baseline"}, (_instr(cache_op, size, src_size=src),)))
    # ignore-src predicate axis (non-foldable predicate)
    for cache_op, size in (("ca", 16), ("cg", 16)):
        cases.append(_case({"cache_op": cache_op, "size": size, "src_size": None, "ignore_src": True, "prefetch": "none", "cache_hint": False, "impl": "canonical", "context": "baseline"}, (_instr(cache_op, size, ignore_src="%p"),), registers_extra=PRED_SETUP[0], preparation_extra=PRED_SETUP[1]))
    # prefetch-size axis
    for cache_op, size, pf in (("ca", 4, "L2::64B"), ("ca", 4, "L2::128B"), ("ca", 4, "L2::256B"), ("cg", 16, "L2::128B")):
        cases.append(_case({"cache_op": cache_op, "size": size, "src_size": None, "ignore_src": False, "prefetch": pf, "cache_hint": False, "impl": "canonical", "context": "baseline"}, (_instr(cache_op, size, prefetch=pf),)))
    # cache_hint axis (operand-form change) and calibrated combination with prefetch
    cases.append(_case({"cache_op": "cg", "size": 16, "src_size": None, "ignore_src": False, "prefetch": "none", "cache_hint": True, "impl": "canonical", "context": "baseline"}, (_instr("cg", 16, cache_hint=True),), cache_hint=True))
    cases.append(_case({"cache_op": "cg", "size": 16, "src_size": None, "ignore_src": False, "prefetch": "L2::256B", "cache_hint": True, "impl": "canonical", "context": "baseline"}, (_instr("cg", 16, prefetch="L2::256B", cache_hint=True),), cache_hint=True))
    return cases


def cp_async_expanded() -> list[Case]:
    cases = cp_async_cases()

    def ctx(context: str, coords_extra: dict, target: tuple[str, ...], observation: tuple[str, ...] = BASE_OBSERVATION, registers_extra: tuple[str, ...] = (), preparation_extra: tuple[str, ...] = (), parameters: tuple[str, ...] = PARAMS) -> Case:
        coords = {"cache_op": "ca", "size": 4, "src_size": None, "ignore_src": False, "prefetch": "none", "cache_hint": False, "impl": "canonical", "context": context}
        coords.update(coords_extra)
        return _case(coords, target, registers_extra=registers_extra, preparation_extra=preparation_extra, observation=observation, parameters=parameters)

    # CTX.pred_foldable: compile-time-true ignore-src folds to the literal !PT operand
    cases.append(ctx("pred_foldable", {"cache_op": "ca", "size": 16, "ignore_src": True}, (_instr("ca", 16, ignore_src="%p"),), registers_extra=(".reg .b32 %t0;", ".reg .pred %p;"), preparation_extra=("mov.u32 %t0, 0;", "setp.eq.u32 %p, %t0, 0;")))
    # CTX.guard: predicated issue of the copy itself
    cases.append(ctx("guarded", {}, (_instr("ca", 4, guard="@%p "),), registers_extra=PRED_SETUP[0], preparation_extra=PRED_SETUP[1]))
    # CTX.inflight_depth: two copies in one group (P0-1 control-word axis)
    cases.append(ctx("depth_2_one_group", {}, ("cp.async.ca.shared.global [%saddr], [%g], 4;", "cp.async.ca.shared.global [%saddr2], [%g2], 4;"), registers_extra=(".reg .b32 %saddr2;", ".reg .b64 %g2;"), preparation_extra=("add.u32 %saddr2, %saddr, 64;", "add.u64 %g2, %g, 64;")))
    # CTX.group_depth: two groups, wait_group 1 / wait_group 0
    two_groups = ("cp.async.ca.shared.global [%saddr], [%g], 4;", "cp.async.commit_group;", "cp.async.ca.shared.global [%saddr2], [%g2], 4;")
    for wait_n in (1, 0):
        cases.append(ctx(f"groups_2_wait_{wait_n}", {}, two_groups, observation=("cp.async.commit_group;", f"cp.async.wait_group {wait_n};", "bar.sync 0;", "ld.shared.b32 %v, [%saddr];", "st.global.b32 [%out], %v;"), registers_extra=(".reg .b32 %saddr2;", ".reg .b64 %g2;"), preparation_extra=("add.u32 %saddr2, %saddr, 64;", "add.u64 %g2, %g, 64;")))
    # CTX.wait_all: wait_all lowers to the LDGDEPBAR + DEPBAR pair without an explicit commit
    cases.append(ctx("wait_all", {}, (_instr("ca", 4),), observation=("cp.async.wait_all;", "bar.sync 0;", "ld.shared.b32 %v, [%saddr];", "st.global.b32 [%out], %v;")))
    # CTX.wait_distance: unrelated work between commit and wait
    filler = tuple("add.u32 %f0, %f0, 1;" for _ in range(8))
    cases.append(ctx("wait_distance_8", {}, (_instr("ca", 4),), observation=("cp.async.commit_group;", *filler, "cp.async.wait_group 0;", "bar.sync 0;", "ld.shared.b32 %v, [%saddr];", "st.global.b32 [%out], %v;"), registers_extra=(".reg .b32 %f0;",), preparation_extra=("mov.u32 %f0, 0;",)))
    # CTX.gaddr_source: global address produced by a load instead of a param
    cases.append(ctx("gaddr_indirect", {}, ("cp.async.ca.shared.global [%saddr], [%g2], 4;",), registers_extra=(".reg .b64 %g2;",), preparation_extra=("ld.global.b64 %g2, [%g];",)))
    # CTX.kernel_template: padded signature moves const-bank offsets (P1-1 axis)
    cases.append(ctx("template_wide", {}, (_instr("ca", 4),), parameters=(".param .u32 p_pad0", ".param .u64 p_g", ".param .u64 p_pad1", ".param .u64 p_out", ".param .u32 p_pad2")))
    return cases


def cp_async_negative() -> list[Case]:
    def probe(coords: dict, target: str, reason: str, diagnostic: str, registers_extra: tuple[str, ...] = (), preparation_extra: tuple[str, ...] = ()) -> Case:
        return Case("", coords, parameters=PARAMS, registers=_registers(False, registers_extra), preparation=_preparation(False, preparation_extra), target=(target,), observation=(), directives=DIRECTIVES, expected="reject", reason=reason, expected_diagnostic=diagnostic)

    return [
        probe({"probe": "size_32"}, "cp.async.ca.shared.global [%saddr], [%g], 32;", "cp-size must be 4, 8 or 16", "expected to be 4 or 8 or 16"),
        probe({"probe": "cg_size_8"}, "cp.async.cg.shared.global [%saddr], [%g], 8;", "cg only accepts cp-size 16", "expected to be 16"),
        probe({"probe": "size_register"}, "cp.async.ca.shared.global [%saddr], [%g], %v;", "cp-size must be an immediate", "Arguments mismatch", preparation_extra=("mov.u32 %v, 4;",)),
        probe({"probe": "src_size_exceeds"}, "cp.async.ca.shared.global [%saddr], [%g], 8, 16;", "src-size must not exceed cp-size", "out of range"),
        probe({"probe": "src_size_plus_pred"}, "cp.async.ca.shared.global [%saddr], [%g], 16, 8, %p;", "src-size and ignore-src cannot be combined", "Arguments mismatch", registers_extra=(".reg .pred %p;",), preparation_extra=("setp.eq.u32 %p, %saddr, 0;",)),
        probe({"probe": "shared_cluster_dst"}, "cp.async.ca.shared::cluster.global [%saddr], [%g], 4;", "classic cp.async writes shared::cta only", "Illegal modifier"),
        # complement sampling outside the assumed-legal surface (P0-2)
        probe({"probe": "prefetch_48B_token"}, "cp.async.ca.shared.global.L2::48B [%saddr], [%g], 4;", "L2::48B is not a defined prefetch size", ""),
    ]


FACTORS = (
    {"id": "SF.cache_op", "levels": ["ca", "cg"]},
    {"id": "SF.size", "levels": [4, 8, 16]},
    {"id": "SF.src_size", "levels": [None, 0, 4, 8, 12]},
    {"id": "SF.ignore_src", "levels": [False, True]},
    {"id": "SF.prefetch", "levels": ["none", "L2::64B", "L2::128B", "L2::256B"]},
    {"id": "SF.cache_hint", "levels": [False, True]},
    {"id": "SF.impl", "levels": ["canonical", "shared_cta_spelling"]},
    {"id": "CTX.context", "levels": ["baseline", "pred_foldable", "guarded", "depth_2_one_group", "groups_2_wait_1", "groups_2_wait_0", "wait_all", "wait_distance_8", "gaddr_indirect", "template_wide"]},
)

SPEC = Spec(
    opcode="cp_async",
    ptx_opcode="cp.async",
    target_patterns=("LDGSTS",),
    factors=FACTORS,
    syntax_cases=cp_async_cases,
    expanded_cases=cp_async_expanded,
    negative_cases=cp_async_negative,
    empty_target_allowed=lambda _coordinates: False,
)

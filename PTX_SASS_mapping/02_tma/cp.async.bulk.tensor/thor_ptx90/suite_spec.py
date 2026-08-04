#!/usr/bin/env python3
"""Independent experiment definition for cp.async.bulk.tensor on Thor.

Every legal-matrix entry was pre-calibrated against ptxas V13.0.88 /
nvdisasm V13.0.85 (`sm_110a`): tile 1d-5d maps to UTMALDG.{1D..5D}, gather4 to
.GATHER4 (2d only), im2col/::w/::w::128 (3d-5d) to .IM2COL/.W/.W128 with a
packed-offset UR operand, multicast to .MULTICAST (shared::cluster dst only),
cta_group::2 to .2CTA, L2::cache_hint to an extra desc[UR] operand; stores map
to UTMASTG with .SCATTER4/.IM2COL. shared::cta vs shared::cluster does not
enter the mnemonic.
"""

from suite_runtime import Case, Spec

LOAD_MODE_TOKENS = {
    "tile": ".tile",
    "gather4": ".tile::gather4",
    "im2col": ".im2col",
    "im2col_w": ".im2col::w",
    "im2col_w128": ".im2col::w::128",
}
STORE_MODE_TOKENS = {
    "tile": ".tile",
    "scatter4": ".tile::scatter4",
    "im2col_no_offs": ".im2col_no_offs",
}
CTA_GROUP_TOKENS = {"none": "", "one": ".cta_group::1", "two": ".cta_group::2"}

SHARED_DECLS = (
    ".shared .align 128 .b8 smem[1024];",
    ".shared .align 8 .b64 mbar;",
)
PARAMS = (".param .u64 p_tmap", ".param .u64 p_out")
DIRECTIVES = (".reqntid 128",)


def _coords(count: int) -> str:
    return "{" + ", ".join(f"%c{index}" for index in range(count)) + "}"


def _load_instr(rank: int, dst: str, mode: str, multicast: bool, cta_group: str, cache_hint: bool, guard: str = "", dst_reg: str = "%saddr", mbar_reg: str = "%maddr", tmap_reg: str = "%tmap") -> str:
    coord_count = 5 if mode == "gather4" else rank
    tail = ""
    if mode == "im2col":
        tail += ", {" + ", ".join(f"%h{index}" for index in range(rank - 2)) + "}"
    elif mode in ("im2col_w", "im2col_w128"):
        tail += ", {%h0, %h1}"
    if multicast:
        tail += ", %hmask"
    if cache_hint:
        tail += ", %pol"
    return (
        f"{guard}cp.async.bulk.tensor.{rank}d.shared::{dst}.global"
        f"{LOAD_MODE_TOKENS[mode]}{CTA_GROUP_TOKENS[cta_group]}.mbarrier::complete_tx::bytes"
        f"{'.multicast::cluster' if multicast else ''}{'.L2::cache_hint' if cache_hint else ''}"
        f" [{dst_reg}], [{tmap_reg}, {_coords(coord_count)}], [{mbar_reg}]{tail};"
    )


def _store_instr(rank: int, mode: str, cache_hint: bool) -> str:
    coord_count = 5 if mode == "scatter4" else rank
    tail = ", %pol" if cache_hint else ""
    return (
        f"cp.async.bulk.tensor.{rank}d.global.shared::cta{STORE_MODE_TOKENS[mode]}.bulk_group"
        f"{'.L2::cache_hint' if cache_hint else ''} [%tmap, {_coords(coord_count)}], [%saddr]{tail};"
    )


def _load_registers(cache_hint: bool, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    regs = [
        *SHARED_DECLS,
        ".reg .b32 %saddr, %maddr, %c0, %c1, %c2, %c3, %c4, %v;",
        ".reg .b16 %h0, %h1, %h2, %hmask;",
        ".reg .b64 %tmap, %out;",
    ]
    if cache_hint:
        regs.append(".reg .b64 %pol;")
    regs.extend(extra)
    return tuple(regs)


def _load_preparation(cache_hint: bool, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    prep = [
        "ld.param.b64 %tmap, [p_tmap];",
        "ld.param.b64 %out, [p_out];",
        "mov.u32 %saddr, smem;",
        "mov.u32 %maddr, mbar;",
        "mov.u32 %c0, 0;",
        "mov.u32 %c1, 0;",
        "mov.u32 %c2, 0;",
        "mov.u32 %c3, 0;",
        "mov.u32 %c4, 0;",
        "mov.b16 %h0, 0;",
        "mov.b16 %h1, 0;",
        "mov.b16 %h2, 0;",
        "mov.b16 %hmask, 3;",
        "mbarrier.init.shared::cta.b64 [%maddr], 1;",
    ]
    if cache_hint:
        prep.append("createpolicy.fractional.L2::evict_last.b64 %pol, 1.0;")
    prep.extend(extra)
    return tuple(prep)


LOAD_OBSERVATION = (
    "bar.sync 0;",
    "ld.shared.b32 %v, [%saddr];",
    "st.global.b32 [%out], %v;",
)


def _load_case(rank: int, dst: str, mode: str, multicast: bool = False, cta_group: str = "none", cache_hint: bool = False) -> Case:
    coords = {"direction": "load", "rank": rank, "dst_space": dst, "mode": mode, "multicast": multicast, "cta_group": cta_group, "cache_hint": cache_hint, "context": "baseline"}
    return Case(
        "",
        coords,
        parameters=PARAMS,
        registers=_load_registers(cache_hint),
        preparation=_load_preparation(cache_hint),
        target=(_load_instr(rank, dst, mode, multicast, cta_group, cache_hint),),
        observation=LOAD_OBSERVATION,
        directives=DIRECTIVES,
    )


def _store_registers(cache_hint: bool) -> tuple[str, ...]:
    regs = [
        SHARED_DECLS[0],
        ".reg .b32 %saddr, %c0, %c1, %c2, %c3, %c4, %t0;",
        ".reg .b64 %tmap, %out;",
    ]
    if cache_hint:
        regs.append(".reg .b64 %pol;")
    return tuple(regs)


def _store_preparation(cache_hint: bool) -> tuple[str, ...]:
    prep = [
        "ld.param.b64 %tmap, [p_tmap];",
        "ld.param.b64 %out, [p_out];",
        "mov.u32 %saddr, smem;",
        "mov.u32 %c0, 0;",
        "mov.u32 %c1, 0;",
        "mov.u32 %c2, 0;",
        "mov.u32 %c3, 0;",
        "mov.u32 %c4, 0;",
        "mov.u32 %t0, %tid.x;",
        "st.shared.b32 [%saddr], %t0;",
        "bar.sync 0;",
    ]
    if cache_hint:
        prep.append("createpolicy.fractional.L2::evict_last.b64 %pol, 1.0;")
    return tuple(prep)


STORE_OBSERVATION = (
    "cp.async.bulk.commit_group;",
    "cp.async.bulk.wait_group 0;",
    "st.global.b32 [%out], %t0;",
)


def _store_case(rank: int, mode: str, cache_hint: bool = False) -> Case:
    coords = {"direction": "store", "rank": rank, "dst_space": "global", "mode": mode, "multicast": False, "cta_group": "none", "cache_hint": cache_hint, "context": "baseline"}
    return Case(
        "",
        coords,
        parameters=PARAMS,
        registers=_store_registers(cache_hint),
        preparation=_store_preparation(cache_hint),
        target=(_store_instr(rank, mode, cache_hint),),
        observation=STORE_OBSERVATION,
        directives=DIRECTIVES,
    )


def bulk_tensor_cases() -> list[Case]:
    cases = []
    # load: tile rank x dst-space full factorial (dst-space is SASS-invariant per calibration)
    for rank in (1, 2, 3, 4, 5):
        for dst in ("cta", "cluster"):
            cases.append(_load_case(rank, dst, "tile"))
    # load: gather4 is 2d-only, both dst spaces
    for dst in ("cta", "cluster"):
        cases.append(_load_case(2, dst, "gather4"))
    # load: im2col family, 3d-5d
    for mode in ("im2col", "im2col_w", "im2col_w128"):
        for rank in (3, 4, 5):
            cases.append(_load_case(rank, "cluster", mode))
    # load: multicast requires shared::cluster dst
    for rank in (1, 2, 5):
        cases.append(_load_case(rank, "cluster", "tile", multicast=True))
    # load: cta_group axis
    cases.append(_load_case(2, "cluster", "tile", cta_group="one"))
    cases.append(_load_case(2, "cluster", "tile", cta_group="two"))
    # load: cache_hint operand-form axis
    cases.append(_load_case(2, "cluster", "tile", cache_hint=True))
    # load: calibrated modifier combinations
    cases.append(_load_case(2, "cluster", "tile", multicast=True, cache_hint=True))
    cases.append(_load_case(2, "cluster", "tile", multicast=True, cta_group="two"))
    cases.append(_load_case(3, "cluster", "im2col", cache_hint=True))
    cases.append(_load_case(3, "cluster", "im2col", multicast=True))
    cases.append(_load_case(2, "cluster", "gather4", multicast=True))
    # store: tile ranks, scatter4 (2d only), im2col_no_offs (3d-5d), cache_hint
    for rank in (1, 2, 3, 4, 5):
        cases.append(_store_case(rank, "tile"))
    cases.append(_store_case(2, "scatter4"))
    for rank in (3, 4, 5):
        cases.append(_store_case(rank, "im2col_no_offs"))
    cases.append(_store_case(2, "tile", cache_hint=True))
    return cases


def bulk_tensor_expanded() -> list[Case]:
    cases = bulk_tensor_cases()

    def context_case(context: str, registers_extra: tuple[str, ...], preparation_extra: tuple[str, ...], target: tuple[str, ...], observation: tuple[str, ...] = LOAD_OBSERVATION, parameters: tuple[str, ...] = PARAMS) -> Case:
        coords = {"direction": "load", "rank": 2, "dst_space": "cluster", "mode": "tile", "multicast": False, "cta_group": "none", "cache_hint": False, "context": context}
        return Case("", coords, parameters=parameters, registers=_load_registers(False, registers_extra), preparation=_load_preparation(False, preparation_extra), target=target, observation=observation, directives=DIRECTIVES)

    # CTX.coord_source: coordinates produced by non-foldable computation
    cases.append(context_case("coord_tid_derived", (".reg .b32 %t0;",), ("mov.u32 %t0, %tid.x;", "mov.u32 %c0, %t0;", "mov.u32 %c1, %t0;"), (_load_instr(2, "cluster", "tile", False, "none", False),)))
    # CTX.tensormap_source: tensormap pointer loaded from memory instead of param
    cases.append(context_case("tensormap_indirect", (".reg .b64 %tmap2;",), ("ld.global.b64 %tmap2, [%tmap];",), (_load_instr(2, "cluster", "tile", False, "none", False, tmap_reg="%tmap2"),)))
    # CTX.mbar_source: mbarrier address derived by arithmetic
    cases.append(context_case("mbar_derived", (".reg .b32 %maddr2;",), ("add.u32 %maddr2, %maddr, 0;",), (_load_instr(2, "cluster", "tile", False, "none", False, mbar_reg="%maddr2"),)))
    # CTX.guard: predicated issue (calibrated: lowers to @!UPx UTMALDG)
    cases.append(context_case("guarded", (".reg .b32 %t0;", ".reg .pred %p;"), ("mov.u32 %t0, %tid.x;", "setp.lt.u32 %p, %t0, 16;"), (_load_instr(2, "cluster", "tile", False, "none", False, guard="@%p "),)))
    # CTX.inflight_depth: scoreboard/control-word axis from the tcgen05 review (P0-1)
    for depth in (2, 4):
        extra_regs = (".reg .b32 %saddr1, %saddr2, %saddr3;",)
        prep = ("add.u32 %saddr1, %saddr, 256;", "add.u32 %saddr2, %saddr, 512;", "add.u32 %saddr3, %saddr, 768;")
        targets = tuple(_load_instr(2, "cluster", "tile", False, "none", False, dst_reg=reg) for reg in ("%saddr", "%saddr1", "%saddr2", "%saddr3")[:depth])
        case = context_case(f"inflight_depth_{depth}", extra_regs, prep, targets)
        cases.append(Case("", dict(case.coordinates, context=f"inflight_depth_{depth}"), parameters=case.parameters, registers=case.registers, preparation=case.preparation, target=case.target, observation=case.observation, directives=case.directives))
    # CTX.spelling: cta_group written after the completion mechanism (accepted alternate grammar)
    coords = {"direction": "load", "rank": 2, "dst_space": "cluster", "mode": "tile", "multicast": False, "cta_group": "two", "cache_hint": False, "context": "spelling_post_cta_group"}
    cases.append(Case("", coords, parameters=PARAMS, registers=_load_registers(False), preparation=_load_preparation(False), target=("cp.async.bulk.tensor.2d.shared::cluster.global.tile.mbarrier::complete_tx::bytes.cta_group::2 [%saddr], [%tmap, {%c0, %c1}], [%maddr];",), observation=LOAD_OBSERVATION, directives=DIRECTIVES))
    # CTX.kernel_template: padded signature moves const-bank offsets (P1-1 axis)
    wide_params = (".param .u32 p_pad0", ".param .u64 p_tmap", ".param .u64 p_pad1", ".param .u64 p_out", ".param .u32 p_pad2")
    cases.append(context_case("template_wide", (), (), (_load_instr(2, "cluster", "tile", False, "none", False),), parameters=wide_params))
    # CTX.wait_distance / CTX.group_depth for the store completion protocol
    filler = tuple("add.u32 %c4, %c4, 1;" for _ in range(8))
    cases.append(Case("", {"direction": "store", "rank": 2, "dst_space": "global", "mode": "tile", "multicast": False, "cta_group": "none", "cache_hint": False, "context": "wait_distance_8"}, parameters=PARAMS, registers=_store_registers(False), preparation=_store_preparation(False), target=(_store_instr(2, "tile", False),), observation=("cp.async.bulk.commit_group;", *filler, "cp.async.bulk.wait_group 0;", "st.global.b32 [%out], %t0;"), directives=DIRECTIVES))
    cases.append(Case("", {"direction": "store", "rank": 2, "dst_space": "global", "mode": "tile", "multicast": False, "cta_group": "none", "cache_hint": False, "context": "group_depth_2_wait_1"}, parameters=PARAMS, registers=_store_registers(False), preparation=_store_preparation(False), target=(_store_instr(2, "tile", False), "cp.async.bulk.commit_group;", _store_instr(2, "tile", False)), observation=("cp.async.bulk.commit_group;", "cp.async.bulk.wait_group 1;", "st.global.b32 [%out], %t0;"), directives=DIRECTIVES))
    return cases


def bulk_tensor_negative() -> list[Case]:
    def probe(coords: dict, target: str, reason: str, diagnostic: str) -> Case:
        return Case("", coords, parameters=PARAMS, registers=_load_registers(False), preparation=_load_preparation(False), target=(target,), observation=(), directives=DIRECTIVES, expected="reject", reason=reason, expected_diagnostic=diagnostic)

    return [
        probe({"probe": "rank_6d"}, "cp.async.bulk.tensor.6d.shared::cluster.global.tile.mbarrier::complete_tx::bytes [%saddr], [%tmap, {%c0, %c1, %c2, %c3, %c4, %c0}], [%maddr];", "tensor rank is limited to 1d-5d", "syntax error"),
        probe({"probe": "missing_completion"}, "cp.async.bulk.tensor.1d.shared::cluster.global.tile [%saddr], [%tmap, {%c0}], [%maddr];", "loads require an explicit completion mechanism", ".completion_mechanism modifier required"),
        probe({"probe": "coord_count_mismatch"}, "cp.async.bulk.tensor.2d.shared::cluster.global.tile.mbarrier::complete_tx::bytes [%saddr], [%tmap, {%c0, %c1, %c2}], [%maddr];", "coordinate vector length must equal rank for tile", "Argument vector size mismatch"),
        probe({"probe": "im2col_b32_offsets"}, "cp.async.bulk.tensor.3d.shared::cluster.global.im2col.mbarrier::complete_tx::bytes [%saddr], [%tmap, {%c0, %c1, %c2}], [%maddr], {%c4};", "im2col offsets must be .b16 registers", "Arguments mismatch"),
        probe({"probe": "store_mbarrier_completion"}, "cp.async.bulk.tensor.2d.global.shared::cta.tile.mbarrier::complete_tx::bytes [%tmap, {%c0, %c1}], [%saddr], [%maddr];", "stores complete via bulk_group, not mbarrier", "Arguments mismatch"),
        probe({"probe": "gather4_rank_3d"}, "cp.async.bulk.tensor.3d.shared::cluster.global.tile::gather4.mbarrier::complete_tx::bytes [%saddr], [%tmap, {%c0, %c1, %c2, %c3, %c4}], [%maddr];", "tile::gather4 is 2d-only", "cannot be combined"),
        probe({"probe": "im2col_rank_2d"}, "cp.async.bulk.tensor.2d.shared::cluster.global.im2col.mbarrier::complete_tx::bytes [%saddr], [%tmap, {%c0, %c1}], [%maddr], {%h0};", "im2col requires rank 3d-5d", "cannot be combined"),
        probe({"probe": "scatter4_on_load"}, "cp.async.bulk.tensor.2d.shared::cluster.global.tile::scatter4.mbarrier::complete_tx::bytes [%saddr], [%tmap, {%c0, %c1, %c2, %c3, %c4}], [%maddr];", "tile::scatter4 exists only on the store direction", "Illegal modifier"),
        probe({"probe": "multicast_cta_dst"}, "cp.async.bulk.tensor.2d.shared::cta.global.tile.mbarrier::complete_tx::bytes.multicast::cluster [%saddr], [%tmap, {%c0, %c1}], [%maddr], %hmask;", "multicast requires shared::cluster destination", "Illegal modifier '.multicast::cluster'"),
        # complement sampling outside the assumed-legal surface (P0-2)
        probe({"probe": "gather4_four_coords"}, "cp.async.bulk.tensor.2d.shared::cluster.global.tile::gather4.mbarrier::complete_tx::bytes [%saddr], [%tmap, {%c0, %c1, %c2, %c3}], [%maddr];", "gather4 requires exactly 5 coordinates", ""),
        probe({"probe": "load_bulk_group_completion"}, "cp.async.bulk.tensor.2d.shared::cluster.global.tile.bulk_group [%saddr], [%tmap, {%c0, %c1}], [%maddr];", "bulk_group is not a load completion mechanism", ""),
        probe({"probe": "multicast_cta_token"}, "cp.async.bulk.tensor.2d.shared::cluster.global.tile.mbarrier::complete_tx::bytes.multicast::cta [%saddr], [%tmap, {%c0, %c1}], [%maddr], %hmask;", "multicast::cta is not a defined token", ""),
    ]


FACTORS = (
    {"id": "SF.direction", "levels": ["load", "store"]},
    {"id": "SF.rank", "levels": [1, 2, 3, 4, 5]},
    {"id": "SF.mode", "levels": ["tile", "gather4", "im2col", "im2col_w", "im2col_w128", "scatter4", "im2col_no_offs"]},
    {"id": "SF.dst_space", "levels": ["cta", "cluster", "global"]},
    {"id": "SF.multicast", "levels": [False, True]},
    {"id": "SF.cta_group", "levels": ["none", "one", "two"]},
    {"id": "SF.cache_hint", "levels": [False, True]},
    {"id": "CTX.context", "levels": ["baseline", "coord_tid_derived", "tensormap_indirect", "mbar_derived", "guarded", "inflight_depth_2", "inflight_depth_4", "spelling_post_cta_group", "template_wide", "wait_distance_8", "group_depth_2_wait_1"]},
)

SPEC = Spec(
    opcode="bulk_tensor",
    ptx_opcode="cp.async.bulk.tensor",
    target_patterns=("UTMALDG", "UTMASTG"),
    factors=FACTORS,
    syntax_cases=bulk_tensor_cases,
    expanded_cases=bulk_tensor_expanded,
    negative_cases=bulk_tensor_negative,
    empty_target_allowed=lambda _coordinates: False,
)

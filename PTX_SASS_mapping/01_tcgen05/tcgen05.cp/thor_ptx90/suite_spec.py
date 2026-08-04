#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.cp on Thor."""

from suite_runtime import Case, Spec

def cp_cases() -> list[Case]:
    shapes = (("128x256b", ""), ("4x256b", ""), ("128x128b", ""), ("64x128b", ".warpx2::02_13"), ("64x128b", ".warpx2::01_23"), ("32x128b", ".warpx4"))
    formats = ("", ".b8x16.b6x16_p32", ".b8x16.b4x16_p64")
    cases = []
    for cta_group in (1, 2):
        for shape, multicast in shapes:
            for fmt in formats:
                coords = {"cta_group": cta_group, "shape": shape, "multicast": multicast.removeprefix(".") or "none", "format": fmt.removeprefix(".") or "none", "taddr_source": "direct", "descriptor_source": "direct"}
                cases.append(Case("", coords, parameters=(".param .u32 p_taddr", ".param .u64 p_desc"), registers=(".reg .b32 %taddr;", ".reg .b64 %desc;"), preparation=("ld.param.b32 %taddr, [p_taddr];", "ld.param.b64 %desc, [p_desc];"), target=(f"tcgen05.cp.cta_group::{cta_group}.{shape}{multicast}{fmt} [%taddr], %desc;",), directives=((".reqntid 128", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 128",))))
    return cases


def cp_expanded() -> list[Case]:
    cases = cp_cases()
    for cta_group in (1, 2):
        for producer in ("identity_derived", "branched"):
            prep = ["ld.param.b32 %base, [p_taddr];", "ld.param.b64 %desc0, [p_desc];", "ld.param.b32 %delta, [p_delta];"]
            if producer == "identity_derived":
                prep += ["add.u32 %taddr, %base, 0;", "add.u64 %desc, %desc0, 0;"]
            else:
                prep += ["setp.ne.u32 %select, %delta, 0;", "add.u32 %alt, %base, %delta;", "selp.b32 %taddr, %alt, %base, %select;", "mov.b64 %desc, %desc0;"]
            cases.append(Case("", {"cta_group": cta_group, "shape": "128x256b", "multicast": "none", "format": "none", "producer": producer}, parameters=(".param .u32 p_taddr", ".param .u64 p_desc", ".param .u32 p_delta"), registers=(".reg .b32 %base, %taddr, %alt, %delta;", ".reg .b64 %desc0, %desc;", ".reg .pred %select;"), preparation=tuple(prep), target=(f"tcgen05.cp.cta_group::{cta_group}.128x256b [%taddr], %desc;",), directives=((".reqntid 128", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 128",))))
        cases.append(Case("", {"cta_group": cta_group, "shape": "128x256b", "guard": "runtime_predicate"}, parameters=(".param .u32 p_taddr", ".param .u64 p_desc", ".param .u32 p_guard"), registers=(".reg .b32 %taddr, %g;", ".reg .b64 %desc;", ".reg .pred %guard;"), preparation=("ld.param.b32 %taddr, [p_taddr];", "ld.param.b64 %desc, [p_desc];", "ld.param.b32 %g, [p_guard];", "setp.ne.u32 %guard, %g, 0;"), target=(f"@%guard tcgen05.cp.cta_group::{cta_group}.128x256b [%taddr], %desc;",), directives=((".reqntid 128", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 128",))))
    return cases


def cp_negative() -> list[Case]:
    bad = (("64x128b", ""), ("32x128b", ""), ("128x256b", ".warpx4"))
    return [Case("", {"shape": shape, "multicast": mc.removeprefix(".") or "none"}, parameters=(".param .u32 p_taddr", ".param .u64 p_desc"), registers=(".reg .b32 %taddr;", ".reg .b64 %desc;"), preparation=("ld.param.b32 %taddr, [p_taddr];", "ld.param.b64 %desc, [p_desc];"), target=(f"tcgen05.cp.cta_group::1.{shape}{mc} [%taddr], %desc;",), expected="reject", reason="shape/multicast pairing violates PTX grammar") for shape, mc in bad]

FACTORS = ({'id': 'SF.cta_group', 'levels': [1, 2]}, {'id': 'SF.shape', 'levels': ['128x256b', '4x256b', '128x128b', '64x128b', '32x128b']}, {'id': 'SF.multicast', 'levels': ['none', 'warpx2::02_13', 'warpx2::01_23', 'warpx4']}, {'id': 'SF.format', 'levels': ['none', 'b8x16.b6x16_p32', 'b8x16.b4x16_p64']}, {'id': 'CTX.producer', 'levels': ['direct', 'identity_derived', 'branched']}, {'id': 'CTX.guard', 'levels': ['unpredicated', 'runtime_predicate']})

SPEC = Spec(
    opcode="cp",
    target_patterns=("UTCCP",),
    factors=FACTORS,
    syntax_cases=cp_cases,
    expanded_cases=cp_expanded,
    negative_cases=cp_negative,
    empty_target_allowed=lambda _coordinates: False,
)


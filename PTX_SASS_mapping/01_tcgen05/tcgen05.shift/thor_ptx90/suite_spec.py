#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.shift on Thor."""

from suite_runtime import Case, Spec

def shift_cases() -> list[Case]:
    return [Case("", {"cta_group": cta_group, "direction": "down", "taddr_source": "direct"}, parameters=(".param .u32 p_taddr",), registers=(".reg .b32 %taddr;",), preparation=("ld.param.b32 %taddr, [p_taddr];",), target=(f"tcgen05.shift.cta_group::{cta_group}.down [%taddr];",), directives=((".reqntid 32", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 32",))) for cta_group in (1, 2)]


def shift_expanded() -> list[Case]:
    cases = shift_cases()
    for cta_group in (1, 2):
        for producer in ("identity_derived", "nonidentity_derived"):
            delta = "0" if producer == "identity_derived" else "%delta"
            cases.append(Case("", {"cta_group": cta_group, "direction": "down", "taddr_source": producer}, parameters=(".param .u32 p_taddr", ".param .u32 p_delta"), registers=(".reg .b32 %base, %taddr, %delta;",), preparation=("ld.param.b32 %base, [p_taddr];", "ld.param.b32 %delta, [p_delta];", f"add.u32 %taddr, %base, {delta};"), target=(f"tcgen05.shift.cta_group::{cta_group}.down [%taddr];",), directives=((".reqntid 32", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 32",))))
        cases.append(Case("", {"cta_group": cta_group, "direction": "down", "guard": "runtime_predicate"}, parameters=(".param .u32 p_taddr", ".param .u32 p_guard"), registers=(".reg .b32 %taddr, %g;", ".reg .pred %guard;"), preparation=("ld.param.b32 %taddr, [p_taddr];", "ld.param.b32 %g, [p_guard];", "setp.ne.u32 %guard, %g, 0;"), target=(f"@%guard tcgen05.shift.cta_group::{cta_group}.down [%taddr];",), directives=((".reqntid 32", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 32",))))
    return cases


def shift_negative() -> list[Case]:
    return [Case("", {"direction": "up"}, parameters=(".param .u32 p_taddr",), registers=(".reg .b32 %taddr;",), preparation=("ld.param.b32 %taddr, [p_taddr];",), target=("tcgen05.shift.cta_group::1.up [%taddr];",), expected="reject", reason="PTX 9.0 only defines down")]

FACTORS = ({'id': 'SF.cta_group', 'levels': [1, 2]}, {'id': 'SF.direction', 'levels': ['down']}, {'id': 'CTX.taddr_source', 'levels': ['direct', 'identity_derived', 'nonidentity_derived']}, {'id': 'CTX.guard', 'levels': ['unpredicated', 'runtime_predicate']})

SPEC = Spec(
    opcode="shift",
    target_patterns=("UTCSHIFT",),
    factors=FACTORS,
    syntax_cases=shift_cases,
    expanded_cases=shift_expanded,
    negative_cases=shift_negative,
    empty_target_allowed=lambda _coordinates: False,
)


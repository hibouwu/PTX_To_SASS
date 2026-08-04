#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.relinquish_alloc_permit on Thor."""

from suite_runtime import Case, Spec

def relinquish_cases() -> list[Case]:
    cases = []
    for cta_group in (1, 2):
        coords = {"cta_group": cta_group, "position": "after_dealloc"}
        cases.append(Case("", coords, (".shared .align 4 .b32 slot;",), registers=(".reg .b32 %taddr;",), preparation=(f"tcgen05.alloc.cta_group::{cta_group}.sync.aligned.shared::cta.b32 [slot], 32;", "ld.shared::cta.b32 %taddr, [slot];", f"tcgen05.dealloc.cta_group::{cta_group}.sync.aligned.b32 %taddr, 32;"), target=(f"tcgen05.relinquish_alloc_permit.cta_group::{cta_group}.sync.aligned;",), directives=((".reqntid 32", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 32",))))
    return cases


def relinquish_expanded() -> list[Case]:
    cases = relinquish_cases()
    for cta_group in (1, 2):
        for guard in ("uniform_parameter", "lane0"):
            prep = ("ld.param.b32 %g, [p_guard];", "setp.ne.u32 %p, %g, 0;") if guard == "uniform_parameter" else ("mov.u32 %g, %laneid;", "setp.eq.u32 %p, %g, 0;")
            cases.append(Case("", {"cta_group": cta_group, "position": "standalone", "guard": guard, "semantic_scope": "static_lowering_only"}, parameters=(".param .u32 p_guard",), registers=(".reg .b32 %g;", ".reg .pred %p;"), preparation=prep, target=(f"@%p tcgen05.relinquish_alloc_permit.cta_group::{cta_group}.sync.aligned;",), directives=((".reqntid 32", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 32",))))
    return cases


def relinquish_negative() -> list[Case]:
    return [Case("", {"cta_group": 3}, target=("tcgen05.relinquish_alloc_permit.cta_group::3.sync.aligned;",), expected="reject", reason="only CTA groups 1 and 2 are legal")]

FACTORS = ({'id': 'SF.cta_group', 'levels': [1, 2]}, {'id': 'CTX.position', 'levels': ['after_dealloc', 'standalone']}, {'id': 'CTX.guard', 'levels': ['unpredicated', 'uniform_parameter', 'lane0']})

SPEC = Spec(
    opcode="relinquish_alloc_permit",
    target_patterns=(),
    factors=FACTORS,
    syntax_cases=relinquish_cases,
    expanded_cases=relinquish_expanded,
    negative_cases=relinquish_negative,
    empty_target_allowed=lambda _coordinates: True,
)


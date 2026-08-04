#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.alloc on Thor."""

from suite_runtime import Case, Spec

def allocation_cases() -> list[Case]:
    cases = []
    for cta_group in (1, 2):
        for state_space in ("generic", "shared_cta"):
            for ncols in (32, 64, 128, 256, 512):
                space = "" if state_space == "generic" else ".shared::cta"
                coords = {"cta_group": cta_group, "state_space": state_space, "ncols": ncols}
                cases.append(Case("", coords, (".shared .align 4 .b32 alloc_slot;",), registers=(".reg .b32 %taddr;",), target=(f"tcgen05.alloc.cta_group::{cta_group}.sync.aligned{space}.b32 [alloc_slot], {ncols};",), observation=("ld.shared::cta.b32 %taddr, [alloc_slot];", f"tcgen05.dealloc.cta_group::{cta_group}.sync.aligned.b32 %taddr, {ncols};", f"tcgen05.relinquish_alloc_permit.cta_group::{cta_group}.sync.aligned;"), directives=((".reqntid 32", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 32",))))
    return cases


def allocation_expanded() -> list[Case]:
    cases = allocation_cases()
    for cta_group in (1, 2):
        for guard in ("uniform_parameter", "lane0"):
            coords = {"cta_group": cta_group, "state_space": "shared_cta", "ncols": 32, "guard": guard, "semantic_scope": "static_lowering_only"}
            prep = ("ld.param.b32 %g, [p_guard];", "setp.ne.u32 %p, %g, 0;") if guard == "uniform_parameter" else ("mov.u32 %g, %laneid;", "setp.eq.u32 %p, %g, 0;")
            cases.append(Case("", coords, (".shared .align 4 .b32 alloc_slot;",), (".param .u32 p_guard",), (".reg .b32 %taddr, %g;", ".reg .pred %p;"), prep, (f"@%p tcgen05.alloc.cta_group::{cta_group}.sync.aligned.shared::cta.b32 [alloc_slot], 32;",), (), ((".reqntid 32", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 32",))))
    return cases


def allocation_negative() -> list[Case]:
    return [Case("", {"ncols": value}, (".shared .align 4 .b32 slot;",), target=(f"tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [slot], {value};",), expected="reject", reason="nCols must be a power of two in [32, 512]") for value in (16, 48, 1024)]

FACTORS = ({'id': 'SF.cta_group', 'levels': [1, 2]}, {'id': 'SF.state_space', 'levels': ['generic', 'shared_cta']}, {'id': 'SF.ncols', 'levels': [32, 64, 128, 256, 512]}, {'id': 'CTX.guard', 'levels': ['unpredicated', 'uniform_parameter', 'lane0']})

SPEC = Spec(
    opcode="alloc",
    target_patterns=("FIND_AND_SET",),
    factors=FACTORS,
    syntax_cases=allocation_cases,
    expanded_cases=allocation_expanded,
    negative_cases=allocation_negative,
    empty_target_allowed=lambda _coordinates: False,
)


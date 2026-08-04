#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.dealloc on Thor."""

from suite_runtime import Case, Spec

def deallocation_cases() -> list[Case]:
    cases = []
    for cta_group in (1, 2):
        for ncols in (32, 64, 128, 256, 512):
            coords = {"cta_group": cta_group, "ncols": ncols, "address_source": "alloc_result"}
            cases.append(Case("", coords, (".shared .align 4 .b32 alloc_slot;",), registers=(".reg .b32 %taddr;",), preparation=(f"tcgen05.alloc.cta_group::{cta_group}.sync.aligned.shared::cta.b32 [alloc_slot], {ncols};", "ld.shared::cta.b32 %taddr, [alloc_slot];"), target=(f"tcgen05.dealloc.cta_group::{cta_group}.sync.aligned.b32 %taddr, {ncols};",), observation=(f"tcgen05.relinquish_alloc_permit.cta_group::{cta_group}.sync.aligned;",), directives=((".reqntid 32", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 32",))))
    return cases


def deallocation_expanded() -> list[Case]:
    cases = deallocation_cases()
    for cta_group in (1, 2):
        coords = {"cta_group": cta_group, "ncols": 32, "address_source": "identity_derived"}
        cases.append(Case("", coords, (".shared .align 4 .b32 alloc_slot;",), registers=(".reg .b32 %base, %taddr;",), preparation=(f"tcgen05.alloc.cta_group::{cta_group}.sync.aligned.shared::cta.b32 [alloc_slot], 32;", "ld.shared::cta.b32 %base, [alloc_slot];", "add.u32 %taddr, %base, 0;"), target=(f"tcgen05.dealloc.cta_group::{cta_group}.sync.aligned.b32 %taddr, 32;",), observation=(f"tcgen05.relinquish_alloc_permit.cta_group::{cta_group}.sync.aligned;",), directives=((".reqntid 32", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 32",))))
    return cases


def deallocation_negative() -> list[Case]:
    cases = [Case("", {"ncols": value}, parameters=(".param .u32 p_taddr",), registers=(".reg .b32 %taddr;",), preparation=("ld.param.b32 %taddr, [p_taddr];",), target=(f"tcgen05.dealloc.cta_group::1.sync.aligned.b32 %taddr, {value};",), expected="reject", reason="ptxas requires nCols to be a multiple of 32") for value in (16, 48)]
    cases.append(Case("", {"cta_group": 3, "ncols": 32}, parameters=(".param .u32 p_taddr",), registers=(".reg .b32 %taddr;",), preparation=("ld.param.b32 %taddr, [p_taddr];",), target=("tcgen05.dealloc.cta_group::3.sync.aligned.b32 %taddr, 32;",), expected="reject", reason="only CTA groups 1 and 2 are legal"))
    return cases

FACTORS = ({'id': 'SF.cta_group', 'levels': [1, 2]}, {'id': 'SF.ncols', 'levels': [32, 64, 128, 256, 512]}, {'id': 'CTX.address_source', 'levels': ['alloc_result', 'identity_derived']})

SPEC = Spec(
    opcode="dealloc",
    target_patterns=("UTCATOMSWS.AND",),
    factors=FACTORS,
    syntax_cases=deallocation_cases,
    expanded_cases=deallocation_expanded,
    negative_cases=deallocation_negative,
    empty_target_allowed=lambda _coordinates: False,
)


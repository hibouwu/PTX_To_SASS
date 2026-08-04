#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.commit on Thor."""

from suite_runtime import Case, Spec

def commit_cases() -> list[Case]:
    cases = []
    for cta_group in (1, 2):
        for state in ("generic", "shared_cluster"):
            for multicast in (False, True):
                declarations = (".shared .align 8 .b64 mbar_obj;",) if state == "shared_cluster" else ()
                parameters = ((".param .u16 p_mask",) if state == "shared_cluster" else (".param .u64 p_mbar", ".param .u16 p_mask"))
                registers = ((".reg .b16 %mask;",) if state == "shared_cluster" else (".reg .b64 %mbar;", ".reg .b16 %mask;"))
                prep = ["ld.param.b16 %mask, [p_mask];"]
                address = "mbar_obj" if state == "shared_cluster" else "%mbar"
                if state == "generic": prep.insert(0, "ld.param.b64 %mbar, [p_mbar];")
                space = ".shared::cluster" if state == "shared_cluster" else ""
                mc = ".multicast::cluster" if multicast else ""
                mask = ", %mask" if multicast else ""
                cases.append(Case("", {"cta_group": cta_group, "state_space": state, "multicast": multicast, "prior_operation": "none"}, declarations, parameters, registers, tuple(prep), (f"tcgen05.commit.cta_group::{cta_group}.mbarrier::arrive::one{space}{mc}.b64 [{address}]{mask};",), directives=((".reqntid 32", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 32",))))
    return cases


def commit_expanded() -> list[Case]:
    cases = commit_cases()
    for cta_group in (1, 2):
        for prior in ("cp", "shift"):
            op = f"tcgen05.cp.cta_group::{cta_group}.128x256b [%taddr], %desc;" if prior == "cp" else f"tcgen05.shift.cta_group::{cta_group}.down [%taddr];"
            cases.append(Case("", {"cta_group": cta_group, "state_space": "shared_cluster", "multicast": False, "prior_operation": prior}, (".shared .align 8 .b64 mbar_obj;",), (".param .u32 p_taddr", ".param .u64 p_desc"), (".reg .b32 %taddr;", ".reg .b64 %desc;"), ("ld.param.b32 %taddr, [p_taddr];", "ld.param.b64 %desc, [p_desc];", op), (f"tcgen05.commit.cta_group::{cta_group}.mbarrier::arrive::one.shared::cluster.b64 [mbar_obj];",), directives=((".reqntid 32", ".reqnctapercluster 2", ".explicitcluster") if cta_group == 2 else (".reqntid 32",))))
    return cases


def commit_negative() -> list[Case]:
    return [Case("", {"cta_group": 3}, (".shared .align 8 .b64 mbar;",), target=("tcgen05.commit.cta_group::3.mbarrier::arrive::one.shared::cluster.b64 [mbar];",), expected="reject", reason="only CTA groups 1 and 2 are legal")]

FACTORS = ({'id': 'SF.cta_group', 'levels': [1, 2]}, {'id': 'SF.state_space', 'levels': ['generic', 'shared_cluster']}, {'id': 'SF.multicast', 'levels': [False, True]}, {'id': 'CTX.prior_operation', 'levels': ['none', 'cp', 'shift']})

SPEC = Spec(
    opcode="commit",
    target_patterns=("UTCBAR",),
    factors=FACTORS,
    syntax_cases=commit_cases,
    expanded_cases=commit_expanded,
    negative_cases=commit_negative,
    empty_target_allowed=lambda _coordinates: False,
)


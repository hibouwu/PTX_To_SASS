#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.fence on Thor."""

from suite_runtime import Case, Spec

def fence_cases() -> list[Case]:
    return [Case("", {"direction": direction, "adjacent": "none"}, target=(f"tcgen05.fence::{direction}_thread_sync;",)) for direction in ("before", "after")]


def fence_expanded() -> list[Case]:
    cases = fence_cases()
    cp_setup = ("ld.param.b32 %taddr, [p_taddr];", "ld.param.b64 %desc, [p_desc];")
    cp_op = "tcgen05.cp.cta_group::1.128x256b [%taddr], %desc;"
    cases.append(Case("", {"direction": "before", "adjacent": "cp_before"}, parameters=(".param .u32 p_taddr", ".param .u64 p_desc"), registers=(".reg .b32 %taddr;", ".reg .b64 %desc;"), preparation=(*cp_setup, cp_op), target=("tcgen05.fence::before_thread_sync;",)))
    cases.append(Case("", {"direction": "after", "adjacent": "cp_after"}, parameters=(".param .u32 p_taddr", ".param .u64 p_desc"), registers=(".reg .b32 %taddr;", ".reg .b64 %desc;"), preparation=cp_setup, target=("tcgen05.fence::after_thread_sync;",), observation=(cp_op,)))
    return cases


def fence_negative() -> list[Case]:
    return [Case("", {"direction": "around"}, target=("tcgen05.fence::around_thread_sync;",), expected="reject", reason="only before and after are defined")]

FACTORS = ({'id': 'SF.direction', 'levels': ['before', 'after']}, {'id': 'CTX.adjacent', 'levels': ['none', 'cp_before', 'cp_after']})

SPEC = Spec(
    opcode="fence",
    target_patterns=("FENCE",),
    factors=FACTORS,
    syntax_cases=fence_cases,
    expanded_cases=fence_expanded,
    negative_cases=fence_negative,
    empty_target_allowed=lambda _coordinates: True,
)


#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.wait on Thor."""

from suite_runtime import Case, Spec

def wait_cases() -> list[Case]:
    return [Case("", {"wait": kind, "prior_queue": "empty"}, target=(f"tcgen05.wait::{kind}.sync.aligned;",), directives=(".reqntid 32",)) for kind in ("ld", "st")]


def wait_expanded() -> list[Case]:
    cases = wait_cases()
    for kind in ("ld", "st"):
        for queue in ("single", "double"):
            prep = ["ld.param.b32 %taddr, [p_taddr];", "mov.b32 %r0, %tid.x;", "mov.b32 %r1, %tid.x;"]
            op = "tcgen05.ld.sync.aligned.32x32b.x2.b32 {%r0, %r1}, [%taddr];" if kind == "ld" else "tcgen05.st.sync.aligned.32x32b.x2.b32 [%taddr], {%r0, %r1};"
            prep.extend([op] * (2 if queue == "double" else 1))
            cases.append(Case("", {"wait": kind, "prior_queue": queue}, parameters=(".param .u32 p_taddr",), registers=(".reg .b32 %taddr, %r0, %r1;",), preparation=tuple(prep), target=(f"tcgen05.wait::{kind}.sync.aligned;",), directives=(".reqntid 32",)))
    return cases


def wait_negative() -> list[Case]:
    return [Case("", {"wait": "cp"}, target=("tcgen05.wait::cp.sync.aligned;",), expected="reject", reason="wait operation is limited to ld and st")]

FACTORS = ({'id': 'SF.wait', 'levels': ['ld', 'st']}, {'id': 'CTX.prior_queue', 'levels': ['empty', 'single', 'double']})

SPEC = Spec(
    opcode="wait",
    target_patterns=("FENCE.VIEW.ASYNC",),
    factors=FACTORS,
    syntax_cases=wait_cases,
    expanded_cases=wait_expanded,
    negative_cases=wait_negative,
    empty_target_allowed=lambda coordinates: coordinates.get("wait") == "ld",
)


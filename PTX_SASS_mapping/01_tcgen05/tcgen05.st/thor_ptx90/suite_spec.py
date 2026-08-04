#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.st on Thor."""

from suite_runtime import Case, Spec


def _tuple(prefix: str, count: int) -> str:
    return "{" + ", ".join(f"%{prefix}{index}" for index in range(count)) + "}"


def _reg_count(shape: str, repeat: int) -> int:
    base = {"16x64b": 1, "16x128b": 2, "16x256b": 4, "32x32b": 1, "16x32bx2": 1}[shape]
    return base * repeat

def st_cases() -> list[Case]:
    cases = []
    for shape in ("16x64b", "16x128b", "16x256b", "32x32b", "16x32bx2"):
        for repeat in (1, 2, 4, 8):
            for unpacked in (False, True):
                count = _reg_count(shape, repeat)
                unpack = ".unpack::16b" if unpacked else ""
                operands = f"[%taddr], 16, {_tuple('r', count)}" if shape == "16x32bx2" else f"[%taddr], {_tuple('r', count)}"
                prep = ["ld.param.b32 %taddr, [p_taddr];"] + [f"mov.b32 %r{index}, %tid.x;" for index in range(count)]
                cases.append(Case("", {"shape": shape, "repeat": repeat, "unpack": unpacked, "taddr_source": "direct", "producer": "tid"}, parameters=(".param .u32 p_taddr",), registers=(f".reg .b32 %r<{count}>;", ".reg .b32 %taddr;"), preparation=tuple(prep), target=(f"tcgen05.st.sync.aligned.{shape}.x{repeat}{unpack}.b32 {operands};",), observation=("tcgen05.wait::st.sync.aligned;",), directives=(".reqntid 32",)))
    return cases


def st_expanded() -> list[Case]:
    cases = st_cases()
    for source in ("identity_derived", "nonidentity_derived"):
        delta = "0" if source == "identity_derived" else "%delta"
        cases.append(Case("", {"shape": "32x32b", "repeat": 2, "unpack": False, "taddr_source": source, "producer": "parameters"}, parameters=(".param .u32 p_taddr", ".param .u32 p_delta", ".param .u32 p_r0", ".param .u32 p_r1"), registers=(".reg .b32 %base, %taddr, %delta, %r0, %r1;",), preparation=("ld.param.b32 %base, [p_taddr];", "ld.param.b32 %delta, [p_delta];", "ld.param.b32 %r0, [p_r0];", "ld.param.b32 %r1, [p_r1];", f"add.u32 %taddr, %base, {delta};"), target=("tcgen05.st.sync.aligned.32x32b.x2.b32 [%taddr], {%r0, %r1};",), observation=("tcgen05.wait::st.sync.aligned;",), directives=(".reqntid 32",)))
    return cases


def st_negative() -> list[Case]:
    return [Case("", {"shape": "8x32b", "repeat": 1}, parameters=(".param .u32 p_taddr",), registers=(".reg .b32 %r, %taddr;",), preparation=("ld.param.b32 %taddr, [p_taddr];", "mov.b32 %r, 0;"), target=("tcgen05.st.sync.aligned.8x32b.x1.b32 [%taddr], {%r};",), expected="reject", reason="shape is outside tcgen05.st grammar")]

FACTORS = ({'id': 'SF.shape', 'levels': ['16x64b', '16x128b', '16x256b', '32x32b', '16x32bx2']}, {'id': 'SF.repeat', 'levels': [1, 2, 4, 8]}, {'id': 'SF.unpack', 'levels': [False, True]}, {'id': 'CTX.taddr_source', 'levels': ['direct', 'identity_derived', 'nonidentity_derived']}, {'id': 'CTX.producer', 'levels': ['tid', 'parameters']})

SPEC = Spec(
    opcode="st",
    target_patterns=("STTM",),
    factors=FACTORS,
    syntax_cases=st_cases,
    expanded_cases=st_expanded,
    negative_cases=st_negative,
    empty_target_allowed=lambda _coordinates: False,
)


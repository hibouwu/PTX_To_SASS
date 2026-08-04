#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.ld on Thor."""

from suite_runtime import Case, Spec


def _tuple(prefix: str, count: int) -> str:
    return "{" + ", ".join(f"%{prefix}{index}" for index in range(count)) + "}"


def _reg_count(shape: str, repeat: int) -> int:
    base = {"16x64b": 1, "16x128b": 2, "16x256b": 4, "32x32b": 1, "16x32bx2": 1}[shape]
    return base * repeat

def ld_cases() -> list[Case]:
    cases = []
    for shape in ("16x64b", "16x128b", "16x256b", "32x32b", "16x32bx2"):
        for repeat in (1, 2, 4, 8):
            for packed in (False, True):
                count = _reg_count(shape, repeat)
                pack = ".pack::16b" if packed else ""
                extra = ", 16" if shape == "16x32bx2" else ""
                coords = {"shape": shape, "repeat": repeat, "pack": packed, "taddr_source": "direct", "consumer": "xor_sink"}
                post = ["mov.b32 %sink, 0;"] + [f"xor.b32 %sink, %sink, %r{index};" for index in range(count)] + ["st.global.b32 [%out], %sink;"]
                cases.append(Case("", coords, parameters=(".param .u32 p_taddr", ".param .u64 p_out"), registers=(f".reg .b32 %r<{count}>;", ".reg .b32 %taddr, %sink;", ".reg .b64 %out;"), preparation=("ld.param.b32 %taddr, [p_taddr];", "ld.param.b64 %out, [p_out];"), target=(f"tcgen05.ld.sync.aligned.{shape}.x{repeat}{pack}.b32 {_tuple('r', count)}, [%taddr]{extra};",), observation=("tcgen05.wait::ld.sync.aligned;", *post), directives=(".reqntid 32",)))
    return cases


def ld_expanded() -> list[Case]:
    cases = ld_cases()
    for source in ("identity_derived", "nonidentity_derived"):
        delta = "0" if source == "identity_derived" else "%delta"
        cases.append(Case("", {"shape": "32x32b", "repeat": 2, "pack": False, "taddr_source": source, "consumer": "global_store"}, parameters=(".param .u32 p_taddr", ".param .u32 p_delta", ".param .u64 p_out"), registers=(".reg .b32 %r<2>, %base, %taddr, %delta;", ".reg .b64 %out;"), preparation=("ld.param.b32 %base, [p_taddr];", "ld.param.b32 %delta, [p_delta];", "ld.param.b64 %out, [p_out];", f"add.u32 %taddr, %base, {delta};"), target=("tcgen05.ld.sync.aligned.32x32b.x2.b32 {%r0, %r1}, [%taddr];",), observation=("tcgen05.wait::ld.sync.aligned;", "st.global.v2.b32 [%out], {%r0, %r1};"), directives=(".reqntid 32",)))
    for typ in ("u32", "s32"):
        for op in ("min", "max"):
            cases.append(Case("", {"variant": "red", "shape": "32x32b", "repeat": 2, "type": typ, "red_op": op}, parameters=(".param .u32 p_taddr", ".param .u64 p_out"), registers=(".reg .b32 %r<2>, %taddr, %red, %sink;", ".reg .b64 %out;"), preparation=("ld.param.b32 %taddr, [p_taddr];", "ld.param.b64 %out, [p_out];", "mov.b32 %red, 0;"), target=(f"tcgen05.ld.red.sync.aligned.32x32b.x2.{typ}.{op} {{%r0, %r1}}, %red, [%taddr];",), observation=("tcgen05.wait::ld.sync.aligned;", "xor.b32 %sink, %r0, %r1;", "xor.b32 %sink, %sink, %red;", "st.global.b32 [%out], %sink;"), directives=(".reqntid 32",)))
    return cases


def ld_negative() -> list[Case]:
    return [Case("", {"shape": "8x32b", "repeat": 1}, parameters=(".param .u32 p_taddr",), registers=(".reg .b32 %r, %taddr;",), preparation=("ld.param.b32 %taddr, [p_taddr];",), target=("tcgen05.ld.sync.aligned.8x32b.x1.b32 {%r}, [%taddr];",), expected="reject", reason="shape is outside tcgen05.ld grammar")]

FACTORS = ({'id': 'SF.variant', 'levels': ['base', 'red']}, {'id': 'SF.shape', 'levels': ['16x64b', '16x128b', '16x256b', '32x32b', '16x32bx2']}, {'id': 'SF.repeat', 'levels': [1, 2, 4, 8]}, {'id': 'SF.pack', 'levels': [False, True]}, {'id': 'SF.reduction', 'levels': ['u32.min', 'u32.max', 's32.min', 's32.max']}, {'id': 'CTX.taddr_source', 'levels': ['direct', 'identity_derived', 'nonidentity_derived']})

SPEC = Spec(
    opcode="ld",
    target_patterns=("LDTM",),
    factors=FACTORS,
    syntax_cases=ld_cases,
    expanded_cases=ld_expanded,
    negative_cases=ld_negative,
    empty_target_allowed=lambda _coordinates: False,
)


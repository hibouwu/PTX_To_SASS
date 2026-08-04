#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.relinquish_alloc_permit on Thor.

实测该指令产生恰好一条 `UVIRTCOUNT.DEALLOC.SMPOOL`，并伴随一次相位字节写入
（`STS.U8 [base+0x1c]`）。用同一 kernel 去掉 relinquish 做单因素对照，`UVIRTCOUNT`
随之消失，`UTCATOMSWS` 的条数不变，因此归属是明确的。

本套件此前把 target_patterns 置空且无条件允许空归属，等于对 SASS 不作任何断言。
现改为断言 `UVIRTCOUNT`，只有显式的对照 case 允许为空。

归属注意事项：alloc 族三条指令通常出现在同一个 kernel 里（后两条是 alloc 的资源
配平），且 alloc 与 dealloc 都 lower 成 `UTCATOMSWS` 家族。按助记符计数会把三者
混为一谈，必须靠子修饰符区分：

    alloc       UTCATOMSWS.FIND_AND_SET.ALIGN（含自旋重试，通常出现两次）
    dealloc     UTCATOMSWS.AND
    relinquish  UVIRTCOUNT.DEALLOC.SMPOOL
"""

from suite_runtime import Case, Spec

SLOT = (".shared .align 4 .b32 slot;",)

GUARDS = {
    "unpredicated": ((), (), ""),
    "uniform_parameter": (
        (".param .u32 p_guard",),
        ("ld.param.b32 %g, [p_guard];", "setp.ne.u32 %p, %g, 0;"),
        "@%p ",
    ),
    "lane0": (
        (),
        ("mov.u32 %g, %laneid;", "setp.eq.u32 %p, %g, 0;"),
        "@%p ",
    ),
}


def _directives(cta_group):
    if cta_group == 2:
        return (".reqntid 32", ".reqnctapercluster 2", ".explicitcluster")
    return (".reqntid 32",)


def _lifecycle(cta_group):
    """alloc 到 dealloc 的完整前序，relinquish 是其收尾。"""
    return (
        f"tcgen05.alloc.cta_group::{cta_group}.sync.aligned.shared::cta.b32 [slot], 32;",
        "ld.shared::cta.b32 %taddr, [slot];",
        f"tcgen05.dealloc.cta_group::{cta_group}.sync.aligned.b32 %taddr, 32;",
    )


def _case(cta_group, position, guard, present):
    guard_params, guard_prep, guard_prefix = GUARDS[guard]
    lifecycle = _lifecycle(cta_group) if position == "after_dealloc" else ()
    registers = [".reg .b32 %taddr;"]
    if guard != "unpredicated":
        registers += [".reg .b32 %g;", ".reg .pred %p;"]
    target = ()
    if present:
        target = (
            f"{guard_prefix}tcgen05.relinquish_alloc_permit"
            f".cta_group::{cta_group}.sync.aligned;",
        )
    coordinates = {
        "cta_group": cta_group,
        "position": position,
        "guard": guard,
        "relinquish_present": present,
    }
    return Case("", coordinates, SLOT if lifecycle else (),
                parameters=guard_params, registers=tuple(registers),
                preparation=(*lifecycle, *guard_prep), target=target,
                directives=_directives(cta_group))


def relinquish_cases() -> list[Case]:
    """语法集：两个 CTA group 的完整生命周期收尾形态。"""
    return [_case(cta_group, "after_dealloc", "unpredicated", True)
            for cta_group in (1, 2)]


def relinquish_expanded() -> list[Case]:
    """扩展集：CTA group × 位置 × guard，各配一个不含 relinquish 的对照。

    对照 case 用于确认 `UVIRTCOUNT.DEALLOC.SMPOOL` 确实由本指令产生，而不是
    alloc 或 dealloc 的副产物。
    """
    cases: list[Case] = []
    for cta_group in (1, 2):
        for position in ("after_dealloc", "standalone"):
            for guard in ("unpredicated", "uniform_parameter", "lane0"):
                cases.append(_case(cta_group, position, guard, True))
            # 每个 (cta_group, position) 配一个无 guard 的对照即可。
            cases.append(_case(cta_group, position, "unpredicated", False))
    return cases


def relinquish_negative() -> list[Case]:
    return [
        Case("", {"cta_group": 3},
             target=("tcgen05.relinquish_alloc_permit.cta_group::3.sync.aligned;",),
             expected="reject", reason="only CTA groups 1 and 2 are legal"),
        Case("", {"cta_group": 1, "qualifier": "missing_sync"},
             target=("tcgen05.relinquish_alloc_permit.cta_group::1.aligned;",),
             expected="reject", reason="sync qualifier is mandatory"),
        Case("", {"cta_group": 1, "operand": "spurious"},
             registers=(".reg .b32 %taddr;",),
             preparation=("mov.b32 %taddr, 0;",),
             target=("tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned %taddr;",),
             expected="reject", reason="the instruction takes no operand"),
    ]


FACTORS = (
    {'id': 'SF.cta_group', 'levels': [1, 2]},
    {'id': 'CTX.position', 'levels': ['after_dealloc', 'standalone']},
    {'id': 'CTX.guard', 'levels': ['unpredicated', 'uniform_parameter', 'lane0']},
    {'id': 'CTX.relinquish_present', 'levels': [True, False]},
)

SPEC = Spec(
    opcode="relinquish_alloc_permit",
    target_patterns=("UVIRTCOUNT",),
    factors=FACTORS,
    syntax_cases=relinquish_cases,
    expanded_cases=relinquish_expanded,
    negative_cases=relinquish_negative,
    # 只有显式的对照 case 允许没有目标指令。
    empty_target_allowed=lambda coordinates: not coordinates.get(
        "relinquish_present", True
    ),
)

#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.fence on Thor.

`tcgen05.fence::{before,after}_thread_sync` 排序的是 tcgen05 异步操作与线程同步
之间的关系。孤立发射这条指令不产生任何可观测效应，因此每个有效 case 必须同时
具备三样东西：一个相邻的 tcgen05 异步操作、一个线程同步点，以及一个不含 fence
的同构对照 case。缺少任何一样，该 case 都只能得出"未产生指令"的空结论。

`tcgen05.fence` 不是内存 fence。`membar.*`/`fence.*` 会产生 `MEMBAR`、`CCTL.IVALL`
等真实指令，本指令一条都不产生，其效应体现在编译器的调度决策上。因此
target_patterns 为空，判据落在与对照 case 的差分上，而不是某条 SASS 是否出现。

已知限制：在本套件当前的形态下，含 fence 与对照的差异只有 fence 位置多出一条
`NOP`，且该 `NOP` 的 wait 掩码为空，自身不承载任何屏障。原因是这些 case 里编译器
本来就没有可重排的余地，因此 fence 的排序作用无从显现。要真正观测该作用，需要
在异步操作与同步点之间放入编译器有动机跨越同步点搬移的独立工作，再比较有无
fence 时该工作是否被搬移。这一轴尚未加入。
"""

from suite_runtime import Case, Spec

CP_PARAMS = (".param .u32 p_taddr", ".param .u64 p_desc")
CP_REGS = (".reg .b32 %taddr;", ".reg .b64 %desc;")
CP_SETUP = ("ld.param.b32 %taddr, [p_taddr];", "ld.param.b64 %desc, [p_desc];")
CP_OP = "tcgen05.cp.cta_group::1.128x256b [%taddr], %desc;"

LD_PARAMS = (".param .u32 p_taddr", ".param .u64 p_out")
LD_REGS = (".reg .b32 %taddr, %r0, %r1, %s;", ".reg .b64 %out;")
LD_SETUP = ("ld.param.b32 %taddr, [p_taddr];", "ld.param.b64 %out, [p_out];")
LD_OP = "tcgen05.ld.sync.aligned.32x32b.x2.b32 {%r0, %r1}, [%taddr];"
LD_CONSUME = ("tcgen05.wait::ld.sync.aligned;", "xor.b32 %s, %r0, %r1;",
              "st.global.b32 [%out], %s;")

# 线程同步形态。tcgen05.fence 的语义完全依附于它，因此这是本套件的主轴。
SYNCS = {
    "none": (),
    "bar_sync": ("bar.sync 0;",),
    "barrier_aligned": ("barrier.sync.aligned 0;",),
}

# 相邻的 tcgen05 异步操作。cp 走 TMEM 拷贝路径，ld 走 TMEM 到寄存器路径。
ADJACENT = {
    "cp": (CP_PARAMS, CP_REGS, CP_SETUP, (CP_OP,), (CP_OP,)),
    "ld": (LD_PARAMS, LD_REGS, LD_SETUP, (LD_OP,), LD_CONSUME),
}

DIRECTIVES = (".reqntid 128",)


def _case(direction, sync, adjacent, fence_present):
    """direction=before 时 fence 位于异步操作与同步之间；after 时位于同步之后。"""
    params, regs, setup, pre_op, post_op = ADJACENT[adjacent]
    fence = (f"tcgen05.fence::{direction}_thread_sync;",) if fence_present else ()
    sync_lines = SYNCS[sync]

    if direction == "before":
        preparation = (*setup, *pre_op)
        observation = (*sync_lines, *post_op)
    else:
        preparation = (*setup, *pre_op, *sync_lines)
        observation = post_op

    coordinates = {
        "direction": direction,
        "sync": sync,
        "adjacent": adjacent,
        "fence_present": fence_present,
    }
    return Case("", coordinates, parameters=params, registers=regs,
                preparation=preparation, target=fence, observation=observation,
                directives=DIRECTIVES)


def fence_cases() -> list[Case]:
    """语法集：只确认两个方向都能被接受，不声称有可观测效应。"""
    return [
        Case("", {"direction": direction, "sync": "none", "adjacent": "none",
                  "fence_present": True},
             target=(f"tcgen05.fence::{direction}_thread_sync;",),
             directives=DIRECTIVES)
        for direction in ("before", "after")
    ]


def fence_expanded() -> list[Case]:
    """扩展集：每个含 fence 的 case 都配一个同构且不含 fence 的对照。

    对照 case 的 target 为空，其存在意义是提供差分基线。判定 fence 是否产生
    效应，靠的是两者的 SASS 差异，而不是 fence case 自身是否出现某条指令。
    """
    cases = fence_cases()
    for direction in ("before", "after"):
        for sync in ("none", "bar_sync", "barrier_aligned"):
            for adjacent in ("cp", "ld"):
                for fence_present in (True, False):
                    cases.append(_case(direction, sync, adjacent, fence_present))
    return cases


def fence_negative() -> list[Case]:
    return [
        Case("", {"direction": "around"},
             target=("tcgen05.fence::around_thread_sync;",),
             expected="reject", reason="only before and after are defined"),
        Case("", {"direction": "before", "suffix": "sync_aligned"},
             target=("tcgen05.fence::before_thread_sync.sync.aligned;",),
             expected="reject",
             reason="tcgen05.fence takes no sync or aligned qualifier"),
    ]


FACTORS = (
    {'id': 'SF.direction', 'levels': ['before', 'after']},
    {'id': 'CTX.sync', 'levels': ['none', 'bar_sync', 'barrier_aligned']},
    {'id': 'CTX.adjacent', 'levels': ['none', 'cp', 'ld']},
    {'id': 'CTX.fence_present', 'levels': [True, False]},
)

SPEC = Spec(
    opcode="fence",
    # tcgen05.fence 不产生任何 SASS 指令，判据在与对照 case 的差分上。
    target_patterns=(),
    factors=FACTORS,
    syntax_cases=fence_cases,
    expanded_cases=fence_expanded,
    negative_cases=fence_negative,
    empty_target_allowed=lambda _coordinates: True,
)

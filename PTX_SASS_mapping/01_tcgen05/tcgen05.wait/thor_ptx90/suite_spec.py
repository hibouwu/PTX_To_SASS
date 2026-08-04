#!/usr/bin/env python3
"""Independent experiment definition for tcgen05.wait on Thor.

`tcgen05.wait::ld` 与 `tcgen05.wait::st` 的 lowering 形态不同，实测：

    tcgen05.wait::ld  ->  不产生指令，效应体现在相邻指令的调度控制位上
    tcgen05.wait::st  ->  产生 FENCE.VIEW.ASYNC.T

原因是两者等待的对象不同。`ld` 等的是 TMEM 到寄存器的结果落地，属于寄存器依赖，
记分牌即可表达；`st` 等的是寄存器到 TMEM 的写入在张量内存视图中可见，属于内存
视图排序，记分牌表达不了，必须发射真实指令。

因此本套件的每个 case 必须具备两样东西：

1. 一个能观测到该等待的消费者。`ld` 的消费者是读取被装入寄存器的后续指令；
   `st` 的消费者是覆盖源寄存器的后续指令，因为 `wait::st` 保护的正是源寄存器
   在被异步读走之前不被改写。没有消费者，等待没有任何可观测效应。
2. 一个不含 wait 的同构对照 case，用于单因素差分。
"""

from suite_runtime import Case, Spec

PARAMS = (".param .u32 p_taddr", ".param .u64 p_out")
REGISTERS = (".reg .b32 %taddr, %r0, %r1, %s;", ".reg .b64 %out;")
SETUP = ("ld.param.b32 %taddr, [p_taddr];", "ld.param.b64 %out, [p_out];")

LD_OP = "tcgen05.ld.sync.aligned.32x32b.x2.b32 {%r0, %r1}, [%taddr];"
ST_OP = "tcgen05.st.sync.aligned.32x32b.x2.b32 [%taddr], {%r0, %r1};"

# ld 的消费者读取被装入的寄存器；st 的消费者覆盖源寄存器。
LD_CONSUMER = ("xor.b32 %s, %r0, %r1;", "st.global.b32 [%out], %s;")
ST_CONSUMER = ("mov.b32 %r0, 7;", "mov.b32 %r1, 9;",
               "xor.b32 %s, %r0, %r1;", "st.global.b32 [%out], %s;")

QUEUE_DEPTH = {"empty": 0, "single": 1, "double": 2, "quad": 4}

DIRECTIVES = (".reqntid 32",)


def _case(kind, queue, wait_present, consumer_present):
    op = LD_OP if kind == "ld" else ST_OP
    consumer = (LD_CONSUMER if kind == "ld" else ST_CONSUMER) if consumer_present else ()
    seed = ("mov.b32 %r0, %tid.x;", "mov.b32 %r1, %tid.x;")
    preparation = (*SETUP, *seed, *([op] * QUEUE_DEPTH[queue]))
    target = (f"tcgen05.wait::{kind}.sync.aligned;",) if wait_present else ()
    coordinates = {
        "wait": kind,
        "prior_queue": queue,
        "wait_present": wait_present,
        "consumer": consumer_present,
    }
    return Case("", coordinates, parameters=PARAMS, registers=REGISTERS,
                preparation=preparation, target=target, observation=consumer,
                directives=DIRECTIVES)


def wait_cases() -> list[Case]:
    """语法集：确认两种形态都被接受。队列为空，不声称有可观测效应。"""
    return [_case(kind, "empty", True, False) for kind in ("ld", "st")]


def wait_expanded() -> list[Case]:
    """扩展集：队列深度 × 有无 wait × 有无消费者。

    `consumer=False` 的行保留下来是为了显示同一条 wait 在没有消费者时退化成
    什么都观测不到，这本身是需要被记录的负面证据。
    """
    cases = list(wait_cases())
    for kind in ("ld", "st"):
        for queue in ("single", "double", "quad"):
            for wait_present in (True, False):
                for consumer_present in (True, False):
                    cases.append(_case(kind, queue, wait_present, consumer_present))
    return cases


def wait_negative() -> list[Case]:
    return [
        Case("", {"wait": "cp"}, target=("tcgen05.wait::cp.sync.aligned;",),
             expected="reject", reason="wait operation is limited to ld and st"),
        Case("", {"wait": "ld", "qualifier": "missing_sync"},
             target=("tcgen05.wait::ld.aligned;",),
             expected="reject", reason="sync qualifier is mandatory"),
        Case("", {"wait": "ld", "qualifier": "missing_aligned"},
             target=("tcgen05.wait::ld.sync;",),
             expected="reject", reason="aligned qualifier is mandatory"),
    ]


FACTORS = (
    {'id': 'SF.wait', 'levels': ['ld', 'st']},
    {'id': 'CTX.prior_queue', 'levels': ['empty', 'single', 'double', 'quad']},
    {'id': 'CTX.wait_present', 'levels': [True, False]},
    {'id': 'CTX.consumer', 'levels': [True, False]},
)

SPEC = Spec(
    opcode="wait",
    target_patterns=("FENCE.VIEW.ASYNC",),
    factors=FACTORS,
    syntax_cases=wait_cases,
    expanded_cases=wait_expanded,
    negative_cases=wait_negative,
    # wait::ld 不产生指令；wait::st 必须产生 FENCE.VIEW.ASYNC。
    # 对照 case 不含 wait，同样允许为空。
    empty_target_allowed=lambda coordinates: (
        coordinates.get("wait") == "ld" or not coordinates.get("wait_present", True)
    ),
)

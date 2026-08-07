# Pass 03：`normalize_predicates`

源码：[`../ptx/src/pass/normalize_predicates.rs`](../ptx/src/pass/normalize_predicates.rs)

## 契约与变换

输入 instruction 可携带 `PredAt`。普通谓词指令变为 `Conditional + true label + instruction + false label`；谓词 `bra` 直接把原目标折入条件边；取反谓词通过交换 true/false target 表示。

输出不变量：`Instruction` 本身无谓词，条件执行只存在于 statement/CFG 层。本 Pass 尚未保证基本块规范，也不判断某个 opcode 是否允许谓词化。

## 顺序依赖

必须在 `normalize_basic_blocks` 前，因为它会创建 label 和边；也必须在任何依赖参与线程集合的分析前完成。

## 现代指令接入

普通可谓词 opcode 通常无需专用修改。对 convergent、collective、async protocol 指令，parser/target validator 必须先定义谓词合法性；若允许，后续协议 Pass 必须按 CFG 路径分析，不能只看词法邻接。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| ISA 禁止谓词化的现代指令 | Pass 对所有 instruction 统一展开 | 会接受到 CFG 层；必须由早期 validator 拒绝 |
| 谓词化 `bra` | `folded_bra` 专门折叠目标 | 已处理 |
| 连续多条谓词指令 | 每条都创建两个匿名 label | 语义可表达但 CFG 膨胀，需后续规范化测试 |

## 测试要求

当前无专属 fixture。补充正/反谓词、谓词 branch、连续谓词、convergent 指令合法/非法组合和 CFG 路径保持测试。

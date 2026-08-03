# `<family-id>` · `<family-name>`

状态：`NOT_STARTED`

## 范围

说明本族包含的 PTX opcode、目标 PTX ISA、架构和明确排除项。

## 指令目录

| PTX opcode | 状态 | 研究边界 |
|---|---|---|
| `<opcode>` | `NOT_STARTED` | `<scope>` |

## 共同高风险交互

- 列出跨 opcode 的生命周期、同步、地址空间、作用域或 producer/consumer 交互。

## 完成门槛

只有当文法边界、静态归属、主要交互、机器编码边界、运行时语义和未覆盖空间均完成记账时，才能把本族标为 `VALIDATED`。

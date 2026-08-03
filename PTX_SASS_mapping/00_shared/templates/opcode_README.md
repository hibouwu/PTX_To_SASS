# `<ptx-opcode>`

状态：`NOT_STARTED`

## 研究边界

- 目标 PTX 形态：
- 明确排除：
- PTX ISA / target：

## 语义因素

| 字段 | 类型 | 水平 | 合法性约束 |
|---|---|---|---|
| `<factor>` | `SF/CTX/RUN/ENV` | `<levels>` | `<constraints>` |

## 待回答的映射问题

- PTX qualifier 如何决定核心 SASS opcode、modifier、操作数槽位和机器编码？
- guard、issuer、producer、consumer 和优化级如何改变外围 lowering？
- 哪些 PTX 形态在 SASS 中发生 alias，哪些字段能够逆向恢复？
- 静态编译结果与运行时语义之间还缺哪些证据？

## 计划产物

`factors.yaml`、`cases/`、`witnesses/`、`results/<env-id>/`、`notes/`和面向人的映射规则文档。

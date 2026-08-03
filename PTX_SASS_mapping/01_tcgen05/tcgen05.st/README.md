# `tcgen05.st`

状态：`NOT_STARTED`

## 研究边界

研究 PTX ISA 9.0、Thor `sm_110a` 上 `tcgen05.st.sync.aligned` 从寄存器到 TMEM 的合法 shape、向量宽度和类型形态，以及相应的 `STTM` 家族、源寄存器组布局和 `tcgen05.wait::st` 协议。

## 主要因素

| 因素 | 计划水平 | 重点问题 |
|---|---|---|
| shape | PTX 9.0 合法 shape | 核心 store opcode 和每线程覆盖区域 |
| vector/type | 合法 `.xN` 与 `.bN` | 源寄存器 tuple 的槽位、宽度和编码 |
| 数据 producer | 参数、算术、load 结果 | producer chain、寄存器压力和融合可能性 |
| TMEM 地址来源 | 参数、alloc 结果、派生地址 | 地址准备、对齐和别名关系 |
| completion | 无 wait、`wait::st`、随后 MMA/cp/dealloc | anti-dependency、可复用和消费者顺序 |

## 完成门槛

需要静态归属、源寄存器到 TMEM 布局、wait 交互、越界/未对齐阴性探针和读回校验；成功发射不等于 store 已完成。

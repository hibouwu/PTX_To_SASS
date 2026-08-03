# `tcgen05.ld`

状态：`NOT_STARTED`

## 研究边界

研究 PTX ISA 9.0、Thor `sm_110a` 上 `tcgen05.ld.sync.aligned` 从 TMEM 到寄存器的合法 shape、向量宽度和类型形态，以及相应的 `LDTM` 家族、寄存器组布局和 `tcgen05.wait::ld` 协议。

## 主要因素

| 因素 | 计划水平 | 重点问题 |
|---|---|---|
| shape | PTX 9.0 合法 shape | 每线程结果数量和核心 SASS 选择 |
| vector/type | 合法 `.xN` 与 `.bN` | 目标寄存器组宽度、顺序和机器编码 |
| TMEM 地址来源 | 参数、alloc 结果、派生地址 | 地址准备、对齐和寄存器类别 |
| consumer | 算术、global/shared store、多次使用 | load 是否拆分、复制、融合或延迟 |
| completion | 无 wait、`wait::ld` | 同线程异步完成与后续 consumer 的边界 |

## 完成门槛

需要核心 `LDTM` 归属、每个 PTX 结果与 SASS register tuple 的槽位映射、wait 交互、O0–O3 lowering 和实机数值 oracle；只验证编译成功不足以说明 TMEM 布局。

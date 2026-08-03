# `tcgen05.shift`

状态：`NOT_STARTED`

## 研究边界

研究 PTX ISA 9.0、Thor `sm_110a` 支持的 `tcgen05.shift` 形态、TMEM 地址/区域操作数和异步完成协议。精确 opcode qualifier、shape 和操作数文法必须在设计阶段依据目标工具链重新冻结，不能从 MMA 的 `.ashift` 推导；`tcgen05.shift` 是独立指令，`.ashift` 是 MMA 操作模式。

## 主要因素

| 因素 | 计划水平 | 重点问题 |
|---|---|---|
| shift 形态 | PTX 9.0 全部合法形式 | 核心 SASS opcode、方向和距离编码 |
| TMEM 地址/区域 | 边界、对齐、重叠与非重叠 | 操作数槽位和未定义行为边界 |
| producer/consumer | MMA、cp、ld/st | 数据依赖、覆盖区域和流水线顺序 |
| completion | commit+mbarrier、fence 组合 | shift 是否被 commit 跟踪以及何时可消费 |
| guard/issuer | 合法参与模式和阴性探针 | 异步发射与谓词 lowering |

## 完成门槛

需要先确认目标工具链 capability，再进行合法文法、核心归属、机器编码、完成协议和实机 TMEM 内容验证。若 `sm_110a` 拒绝规范形态，应记录为 `TARGET_UNSUPPORTED`，不能记成规范非法。

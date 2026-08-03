# `tcgen05.alloc`

状态：`NOT_STARTED`

## 研究边界

研究 PTX ISA 9.0、Thor `sm_110a` 上 `tcgen05.alloc.cta_group::{1,2}.sync.aligned[.shared::cta].b32` 的 PTX→SASS 映射，以及 TMEM 列分配结果的发布方式。独立实验必须把 CTA group、地址写法、结果消费者和完整 warp 参与条件分开操纵。

## 主要因素

| 因素 | 计划水平 | 重点问题 |
|---|---|---|
| CTA group | `1`、`2` | 是否选择不同分配指令、资源数量或参与协议 |
| 地址形式 | generic、`shared::cta` | 核心操作是否 alias，地址 materialization 是否不同 |
| 结果使用 | 单次、多次、跨同步边界 | 分配结果位于 GPR、UR 还是 shared memory，是否出现额外搬运 |
| issuer/participation | 完整 warp、非法部分参与探针 | `.sync.aligned` 的静态 lowering 与运行时参与约束 |

## 完成门槛

需要同时给出合法/非法文法、核心分配 SASS、地址准备、结果发布、CTA group 交互、机器编码和实机资源生命周期验证；仅在 MMA effect slice 中观察到分配序列不算本指令已完成。

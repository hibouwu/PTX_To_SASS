# `tcgen05.relinquish_alloc_permit`

状态：`FRAMEWORK_VALIDATED`（静态实验框架已通过 CUDA 13.0 O0–O3 自检；规则文档待由结果继续归纳）

实验入口：[`thor_ptx90/`](thor_ptx90/)

## 研究边界

研究 `tcgen05.relinquish_alloc_permit.cta_group::{1,2}.sync.aligned` 的核心 SASS、CTA group 差异和它在 TMEM 分配生命周期中的位置。它表示放弃分配许可，不等同于释放已分配的 TMEM。

## 主要因素

| 因素 | 计划水平 | 重点问题 |
|---|---|---|
| CTA group | `1`、`2` | 许可状态和参与集合是否选择不同编码 |
| 相对位置 | alloc 前、alloc 后、dealloc 后 | 哪些序列规范合法、工具链接受、运行时安全 |
| guard/participation | 无 guard、uniform guard、部分参与阴性探针 | `.sync.aligned` 是否产生外围控制流限制 |
| 优化级 | O0–O3 | 无显式数据结果的指令是否被保留、合并或重排 |

## 完成门槛

需要区分编译器接受性、独立或空 lowering、相对位置和优化级变化，并保存规范违规序列的静态接受或拒绝结果。许可状态的运行时行为和资源可复用性不属于完成条件。

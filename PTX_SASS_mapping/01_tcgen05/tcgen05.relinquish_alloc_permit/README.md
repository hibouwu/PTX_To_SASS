# `tcgen05.relinquish_alloc_permit`

状态：`NOT_STARTED`

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

需要区分编译器接受性、核心 lowering、许可状态语义和资源可复用性，并保存违规序列的异常或运行时结果。

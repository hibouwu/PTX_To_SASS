# `tcgen05.commit`

状态：`NOT_STARTED`

## 研究边界

研究 `tcgen05.commit.cta_group::N.mbarrier::arrive::one[.shared::cluster][.multicast::cluster].b64` 的独立映射。MMA 套件已经提供协议见证，但本目录需要穷举 commit 自身的 CTA group、地址形式、multicast mask、前序异步操作和 mbarrier consumer。

## 主要因素

| 因素 | 计划水平 | 重点问题 |
|---|---|---|
| CTA group | `1`、`2` | `UTCBAR`/`.2CTA` 与机器编码 |
| barrier 地址 | generic、`shared::cluster` | 核心 alias 与地址 materialization |
| multicast | 无、cluster mask | `.MULTICAST`、mask 操作数和参与 CTA |
| 前序异步操作 | MMA、cp、shift、混合序列 | commit 跟踪集合和 sequence boundary |
| completion consumer | test/try wait、phase reuse | mbarrier phase、arrival count 和 acquire 连接 |

## 完成门槛

需要独立冻结 commit 文法、核心 `UTCBAR*`、地址和 mask lowering、前序操作交互、机器编码与实机 mbarrier phase 行为。现有 [`tcgen05.mma` 内存一致性文档](../tcgen05.mma/thor_ptx90/Docs/mapping_rules/memory_consistency.md)只能作为已有见证入口。

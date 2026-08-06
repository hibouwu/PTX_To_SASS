# 15 · Cluster 与 DSMEM

状态：`IN_PROGRESS`（[实验设计.md](实验设计.md) 已完成校准；`mapa` 套件已建成并通过首轮自检：10 syntax + 24 expanded case × O0–O3 共 136 次编译/归属 PASS，8 个带诊断锚定的负向探针全部按预期拒绝。关键发现：sm_110a 完整支持 cluster 编译面但**无任何专用 cluster SASS 指令**——mapa 合成为 `S2R SR_CgaCtaId`+`LEA`+`PRMT` rank 嫁接序列；`.reqnctapercluster` 使所有 shared 地址计算携带 rank 标签；cvta 的 u32 形态在 sm_90+ 整体 fatal）

## 范围

覆盖 cluster rank/address mapping、shared::cluster load/store、地址空间转换与判定。

## 具体指令目录

- [`mapa`](mapa/)
- [`getctarank`](getctarank/)
- [`cvta`](cvta/)
- [`isspacep`](isspacep/)
- [`ld.shared-cluster`](ld.shared-cluster/)
- [`st.shared-cluster`](st.shared-cluster/)

## 优先上下文

- local/remote rank、cluster shape 和 launch 属性；
- shared/cluster 地址来源、转换链、对齐和 offset；
- remote load/store、别名、宽度和 memory order；
- mbarrier remote arrive、cluster barrier 和可见性；
- predicate、leader 线程、跨 CTA producer/consumer。

## 跨族依赖

协议可依赖 `03_mbarrier`、`04_fence` 和 `07_lsu`；本目录仍独立生成和验证自己的 testcase。

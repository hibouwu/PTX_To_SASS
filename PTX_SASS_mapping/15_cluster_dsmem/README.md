# 15 · Cluster 与 DSMEM

状态：`NOT_STARTED`

## 范围

覆盖 cluster rank/address mapping、shared::cluster load/store、地址空间转换与判定。

## 优先上下文

- local/remote rank、cluster shape 和 launch 属性；
- shared/cluster 地址来源、转换链、对齐和 offset；
- remote load/store、别名、宽度和 memory order；
- mbarrier remote arrive、cluster barrier 和可见性；
- predicate、leader 线程、跨 CTA producer/consumer。

## 跨族依赖

协议可依赖 `03_mbarrier`、`04_fence` 和 `07_lsu`；本目录仍独立生成和验证自己的 testcase。


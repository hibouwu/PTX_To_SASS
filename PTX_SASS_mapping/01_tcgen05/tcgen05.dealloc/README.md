# `tcgen05.dealloc`

状态：`NOT_STARTED`

## 研究边界

研究 PTX ISA 9.0、Thor `sm_110a` 上 `tcgen05.dealloc.cta_group::{1,2}.sync.aligned.b32` 如何释放 TMEM，以及释放与先前 MMA、copy、load/store 完成之间的必要顺序。

## 主要因素

| 因素 | 计划水平 | 重点问题 |
|---|---|---|
| CTA group | `1`、`2` | `.2CTA` 或资源回收协议如何进入 SASS |
| 地址来源 | 参数、alloc 结果、等价派生链 | 地址生产是否被消除或改变寄存器类别 |
| 前序操作 | 无、MMA、copy、load、store | 编译器是否保留完成等待或只依赖程序员协议 |
| guard/issuer | uniform、divergent、完整 warp | collective 参与约束和谓词 lowering |

## 完成门槛

静态映射之外必须以实机用例验证未完成操作前回收、正确等待后回收、CTA group 2 peer 生命周期和重复分配；不得把成功汇编解释成安全回收。

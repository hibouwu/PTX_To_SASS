# `tcgen05.dealloc`

状态：`FRAMEWORK_VALIDATED`（静态实验框架已通过 CUDA 13.0 O0–O3 自检；规则文档待由结果继续归纳）

实验入口：[`thor_ptx90/`](thor_ptx90/)

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

需要覆盖 nCols、CTA group、地址 producer、guard、前序操作和 O0–O3 lowering，归纳完整回收序列及机器编码。成功汇编只表示静态接受，不能解释成安全回收；运行时资源安全不属于完成条件。

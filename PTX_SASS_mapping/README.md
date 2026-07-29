# PTX 上下文敏感 SASS lowering 实验

本目录研究上下文如何改变 PTX lowering。它与 `verification_num_mapping/` 是两个独立实验：

- `verification_num_mapping/` 只提供本目录最初的指令族分类参考；
- 本目录独立生成 testcase、编译产物、结果、证据状态和结论；
- 另一个实验的成功、失败、白名单或 runtime 状态不能计入本实验的覆盖率；
- 两个实验即使研究相同 opcode，也分别回答自己的研究问题。

通用实验设计见 [实验设计.md](实验设计.md)，共享目录约定见
[00_shared/README.md](00_shared/README.md)。

## 指令族目录

| 目录 | 本实验中的范围 | 优先研究问题 |
|---|---|---|
| `01_tcgen05` | tcgen05 MMA、TMEM copy/load/store、生命周期和 fence | descriptor、寄存器类别、参与协议和完成协议如何共同改变 lowering |
| `02_tma` | tensor bulk async、classic `cp.async`、commit/wait/prefetch | tensor map、维度、swizzle、multicast、mbarrier 和 proxy fence 的交互 |
| `03_mbarrier` | init、arrive、transaction、wait、phase 和 inval | 生命周期、phase、scope、predicate 与 producer/consumer 协议 |
| `04_fence` | proxy fence、memory fence、cluster barrier、barrier | order、scope、proxy、相邻内存操作和控制流边界 |
| `05_cuda_core_int` | 整数算术、逻辑、移位、比较、选择和 move | 立即数、源槽、融合、宽位展开、carry/sat 和 def-use |
| `06_cuda_core_fp` | F32/F64 算术、特殊函数和类型转换 | 舍入、FTZ、NaN、近似语义、融合和转换折叠 |
| `07_lsu` | global/shared/local/const/param 的 load/store | 地址折叠、别名、对齐、宽度、cache policy 和内存顺序 |
| `08_control_flow` | branch、return 和基础控制操作 | predicate、分支布局、跨块活跃性、call/return 和代码移动 |
| `09_special_reg` | special register 读取及其值传播 | special register 种类、uniformity、目标寄存器类别和 consumer |
| `10_atomic` | global/shared atomic 与 reduction | operation、width、state space、order、scope、返回值使用和 contention 语义 |
| `11_half_precision` | F16/F16x2 算术、比较和 modifier | packed lane、源槽 modifier、FTZ/舍入、融合和 pack/unpack |
| `12_bf16` | BF16/BF16x2 算术和 modifier | packed lane、转换 producer、融合、精度约束和寄存器类别 |
| `13_warp_comm` | shuffle、redux、vote、match 和 elect | mask、收敛性、predicate、uniform result 和 consumer pattern |
| `14_bit_ops` | lop3、prmt、bfe/bfi、popc、clz、brev、fns、bmsk | 位掩码立即数、modifier、pattern fusion 和 descriptor consumer |
| `15_cluster_dsmem` | cluster 地址、rank、DSMEM load/store | cluster scope、remote rank、地址转换、barrier 和别名 |
| `16_megakernel_ctrl` | warp barrier、nanosleep、grid dependency、prefetch | 控制协议、可移动边界、predicate、循环和跨 kernel 依赖 |
| `17_quantization` | dp4a/dp2a、pack、FP8 conversion | signedness、sat、rounding、pack layout、accumulator 和融合 |
| `18_activation` | tanh/ex2 等 activation lowering | 输入位型、approx/FTZ、精度、packed 类型和消费者 |

所有指令族初始状态均为 `NOT_STARTED`。状态只能由本目录自己的证据推进。

## 跨族 pattern 的归属

一个 testcase 只设一个 owner，避免相同结果在多个目录重复计数：

1. 研究某条目标 PTX 的 lowering 时，由目标 PTX 所属指令族持有 testcase。
2. producer、consumer、barrier 或 ABI 只作为 `dependencies` 登记。
3. 研究融合时，由被替代的目标语义 pattern 所属族持有；例如 `mul + add → IMAD`
   默认放在 `05_cuda_core_int`。
4. 研究完整协议时，由发起协议的指令族持有；例如 TMA 使用 mbarrier 的组合放在
   `02_tma`，同时声明依赖 `03_mbarrier`。
5. 跨族 testcase 不会自动证明依赖指令族已经完成覆盖。

## 每个指令族的最小交付物

每个目录最终应独立包含：

- 有界的合法指令形态和上下文因子表；
- testcase 清单及生成器版本；
- 完整环境元组和编译命令；
- 原始 PTX、cubin、反汇编、日志与资源信息；
- exact、allocation、semantic 三层 fingerprint；
- 每种候选 lowering 的最小 witness；
- 语法合法、编译成功、目标消失、上下文未实现、无法归属等完整状态账本；
- 当前覆盖率、未覆盖组合和不确定结论。


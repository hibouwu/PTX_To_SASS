# PTXAS `-O0` 到 `-O3` 优化与指令融合实验

这套实验回答两个不同的问题：

1. 同一个 PTX case 在 `-O0/-O1/-O2/-O3` 下，SASS、寄存器数、cubin
   大小和编译时间何时发生变化；
2. 两条 PTX 是否被选择成一条 SASS（FFMA、IMAD、LOP3、LEA/地址折叠），
   以及这种选择是否真的由优化级别触发。

PTX 是虚拟 ISA，因此“`O0`”不等于逐条直译。合法化和目标指令选择在
`O0` 也必须执行，某些融合很可能从 `O0` 就存在。实验以实际反汇编为准，
不预设 `O3` 一定比 `O2` 少指令。

## 运行

```bash
cd flag_research
./run.sh --arch sm_80
```

也可以测试其他实际架构；源码的最低目标是 `sm_80`：

```bash
./run.sh --arch sm_89 --out results/sm_89
./run.sh --arch sm_100a --out results/sm_100a
```

主要输出：

- `results/report.md`：O0–O3 指令数、首次变化级别、融合标志；
- `results/sass_matrix.csv`：每个 case 的完整助记符序列和直方图；
- `results/build_metrics.csv`：编译耗时、cubin 大小、寄存器数；
- `results/sass/*.sass`：必须最终人工核对的完整反汇编；
- `results/log/*.log`：`ptxas -v` 原始日志和错误；
- `results/toolchain.txt`：工具链、架构、主机和运行时间。

`06_fma_contract` 故意使用不带显式舍入修饰符的 `mul.f32/add.f32`，并
会对每个优化级别额外编译一次 `-fmad=false`。如果
baseline 出现 `FFMA` 而该对照不出现，才能把它可靠归因于允许的浮点收缩。
`07_fma_blocked_rounding` 则用 `mul.rz` 验证显式中间舍入会阻止收缩。

## Case 覆盖

| case | 要验证的行为 |
|---|---|
| `01_dead_code` | 死代码删除 |
| `02_constant_fold` | 常量折叠/传播 |
| `03_copy_propagation` | copy propagation |
| `04_constant_branch` | 常量谓词与分支消除 |
| `05_common_subexpression` | 公共子表达式消除 |
| `06_fma_contract` | `mul+add -> FFMA`，含 `-fmad=false` 对照 |
| `07_fma_blocked_rounding` | 舍入模式阻止 FFMA 的负例 |
| `08_integer_imad` | `mul+add -> IMAD` |
| `09_boolean_lop3` | 两级布尔表达式 `-> LOP3.LUT` |
| `10_shift_add_lea` | shift/add 地址生成选择 |
| `11_load_address_fold` | 常量地址偏移折入 load |

## 如何判断“什么时候融合”

先看 `report.md` 的 `fusion marker by level`，再打开对应 SASS 核对操作数。
第一次出现目标 opcode 的级别是这版工具链/该架构上的观测阈值。如果
O0 已出现，结论应写成“目标指令选择阶段已经完成”，而不是“O0 做了
高级优化”。如果 O0–O3 都不变，也不代表优化开关无效，只代表这个最小
case 没有触发级别相关的 pass。

跨 CUDA 版本或 GPU 架构的结论必须分别保存结果目录后比较；PTXAS 的
内部 pass 与各 `-O` 的精确组成不是稳定公开接口。

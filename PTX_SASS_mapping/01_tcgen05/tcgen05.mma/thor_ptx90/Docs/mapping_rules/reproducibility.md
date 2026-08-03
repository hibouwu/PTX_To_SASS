# Thor 主机复现与跨工具链稳定性

> 本页记录 v3 矩阵在两份 CUDA 13.0 二进制之间的历史独立复现实验，因此保留 576 次 expanded 编译、52,736 条 occurrence 和 32,256 个上下文配对等当时计数。当前 v4 Thor 最终矩阵的规模与状态见 [`README.md`](README.md)，不要把两批分母混用。

## 结论

同一套 v3 PTX ISA 9.0、编译目标 `sm_110a` 实验在两份不同 SHA-256 的 CUDA 13.0 `ptxas`/`nvdisasm` 二进制上重新生成后，核心归属（attribution）、上下文差分、guard/发射线程决策规则、机器编码 mask、逆映射统计和协议层有序检查均保持不变。该批静态 PTX → SASS 映射规则因此不只是一次编译产物上的观察——已经通过一次独立工具链二进制复现。

这次复现在 NVIDIA Thor 主机上完成，`check_all.sh` 的验证范围是静态汇编和反汇编。

## 两次实验

| 实验 | Git 结果版本 | `ptxas` | `ptxas` SHA-256 | `nvdisasm` | `nvdisasm` SHA-256 |
|---|---|---|---|---|---|
| 原完整重跑 | `79a5f84` | CUDA 13.0 V13.0.88 | `daba837a68265cae38c832d13399b61dab811891de9b8914defddef143b849f2` | CUDA 13.0 V13.0.85 | `3c27bded09bd877807207b62db8186a0a9a359d10311ab6e2c885f9b418c9f41` |
| Thor 主机重跑 | `b8f3130` | CUDA 13.0 V13.0.88 | `a1941a04ca4fd233b2fbe50c625b1e72b3d5f79ebe80209a272c85482dfbb487` | CUDA 13.0 V13.0.85 | `bc40070d596fa49b81c0905ca1d05e457aaec071280f742997d4a0b511781b25` |

两个 `ptxas` 的版本号和 compiler build ID 相同，但二进制 SHA-256 与内部构建时间不同。两个 `nvdisasm` 也具有相同版本号和 build ID、不同二进制 SHA-256。这里证明的是同一 CUDA 13.0 release/build 系列内的二进制复现，不应外推成跨 CUDA 大版本稳定性。

Thor 主机当时的 v3 `check_all.sh` 结果为：

| 验证层 | Thor 主机结果 |
|---|---|
| syntax 编译 | 72/72 通过 |
| expanded 编译 | 576/576 通过 |
| expanded attribution | 36,864/36,864 case 完成，52,736/52,736 occurrence 归属 |
| protocol 编译与有序 SASS 检查 | 196/196、196/196 通过 |
| 阴性探针 | 11/11 得到预期拒绝 |
| guard/issuer 公式 | 各 1,152/1,152 通过 |

## 机器可核验的不变量

规则分析器记录的三个输入摘要在两次实验中完全相同：

| 输入 | 记录数或作用 | 两次实验共同的 SHA-256 |
|---|---|---|
| expanded manifest | 生成设计与 PTX occurrence 身份 | `7eca829679f645da72e04c193113660e2dab42566534e1558cc45d53814a6021` |
| SASS attribution | 52,736 条 PTX occurrence → 核心 SASS 归属 | `81d5bedf1d2ac1bcdec14e259ce704ade589854a62fb78f23156f7126abce590` |
| context differences | 32,256 个上下文配对差分 | `14d2567002fcffb06612519d9ac2f97f2621ab3168d64b727a2fefe86b823314` |

输入摘要相同意味着不是只比较了汇总计数：逐 occurrence 的核心操作、两个 64-bit encoding word 以及逐配对上下文差分都相同。在删除生成时间、绝对路径和工具链 provenance 后，两份历史 v3 `mapping_rule_analysis.json` 逐字段完全相同，因此以下结论全部复现。仓库当前同名文件已经是 v4 结果，不能拿它直接复核本节列出的 v3 摘要。

- guard：1,152 个设计，352 个首 occurrence 核心谓词化、800 个外围控制流，手写公式 1,152/1,152 通过。
- 发射线程：1,152 个设计，168 个 O1–O3 纯寄存器重编号、984 个稳定布局，手写公式 1,152/1,152 通过。
- 编码：`.2CTA`、`.ASHIFT`、`.A/B_KEEP`、`.BUFFER1/2/3`、`.4X` 和 `.WS` 的 witness 数、候选 pair、置位/清位方向和 XOR mask 全部相同。
- 逆映射：O3 `runtime_zero` 的 1,648 个 occurrence、1,152 种 PTX 指令文本、300 种规范核心 SASS signature 及每个字段的可恢复率全部相同。

syntax、expanded、阴性探针和协议报告在删除耗时、绝对路径与工具二进制 provenance 后也逐字段完全相同。历史 v3 协议层为 196/196 次编译通过、196/196 个有序 SASS 检查通过；仓库当前的 [`protocol-layers/compile_report.json`](../../results/protocol-layers/compile_report.json) 是 v4 重跑结果，只能确认同一组 196 项检查在 v4 仍通过，不能充当历史 v3 两份产物的逐文件复现证据。

## 唯一观测到的 SASS 文本差异

协议层 O1、O2、O3 的原始 SASS 文件逐文件相同。28 个 O0 文件各有一次相邻自搬运顺序交换：

```text
MOV R2, R2
MOV R0, R0

↕

MOV R0, R0
MOV R2, R2
```

全部 raw diff 只有 `MOV R0, R0` 与 `MOV R2, R2`，没有目标 `UTC*MMA`、谓词、分支、barrier、fence、wait 或数据相关操作发生变化。这种 O0 无效自搬运的排列不是稳定映射规则，不应写入正向规则或逆向器。协议检查和规则挖掘忽略它是正确的。

## 这次复现提高了什么证据等级

| 结论 | 复现后的判断 |
|---|---|
| 核心 SASS 指令选择 | 在两份 CUDA 13.0 二进制上逐 occurrence 相同 |
| v3 已隔离的机器编码 mask | 在两份 CUDA 13.0 二进制上相同；不包含 v4 新增字段 |
| guard、发射线程和 producer 编译降级 | 逐配对差分与预测公式相同 |
| completion/内存一致性静态协议 | 四优化级的有序检查相同 |
| O0 无语义调度填充 | 对二进制构建敏感，不进入稳定规则 |
| v4 新增的完整 predicate selector、UR 槽位和 idesc 相邻关系 | 未纳入这次历史双二进制复现；当前只有一组 Thor 二进制证据 |

当前仍需谨慎的边界不是“结果是否来自 Thor 主机”，而是样本域和工具链域：规则只对已生成的 PTX ISA 9.0、编译目标 `sm_110a` 合法矩阵以及当前 CUDA 13.0 build 系列负责。跨 CUDA release 的变化必须用同样的逐记录比较重新验证。

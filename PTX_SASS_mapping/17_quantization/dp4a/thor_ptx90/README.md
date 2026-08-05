# `dp4a` Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：14 个 syntax + 26 个 expanded case 于 O0–O3 共 160 次编译、反汇编与 `IDP.4A` 归属全部通过，0 次编译失败、0 次目标缺失；10 个负向探针全部按预期拒绝且诊断子串匹配）

## 目标

本目录用与 `01_tcgen05`/`02_tma` 相同的静态证据结构研究 `dp4a`：有限合法语法矩阵（signedness × 操作数来源）、受控上下文变化（indirect producer、guard、模板宽度、累加器链）、O0–O3 编译、带机器编码的反汇编、目标指令归属、正向/逆向规则候选及预期拒绝边界。运行时语义（点积数值是否正确）不属于本套件的通过条件，归入 `17_quantization/实验设计.md` 的 `STATIC_ONLY` 边界声明。

本目录是独立、自包含的实验套件，不导入其他指令目录或跨指令公共脚本；`suite_spec.py` 冻结本指令专用因素、case、阴性边界和 SASS matcher，`suite_runtime.py`（`00_shared/templates/suite_runtime.py` 的逐字拷贝，`family="quant"`）只服务本目录的生成、编译、归属与分析入口。

## 一键运行

```bash
cd PTX_SASS_mapping/17_quantization/dp4a/thor_ptx90
./check_all.sh 8
```

结果目录需要放在大容量磁盘时，把第二个参数指定为独立路径：

```bash
./check_all.sh 8 /xplorer/shijy/quant-results/dp4a
```

## 语法矩阵摘要

- `SF.atype` × `SF.btype`（各 `{u32, s32}`，四种符号组合）在 `b`/`c` 均为寄存器来源时的基线四例；
- `SF.b_class`：`b` 操作数寄存器 vs 立即数，四种签名各一例（已实测立即数合法：O0 物化进 GPR，O3 走 `UR`）；
- `SF.c_source`：累加器 `c` 寄存器 vs 立即数，四种签名各一例（已实测立即数合法：O0/O3 均落 GPR，与 `b` 槽的 `UR` 路由不对称）；
- 双修饰符组合（P0-3）：`b`、`c` 同时为立即数，两种签名各一例；
- expanded 追加：`a`/`b`/`c` 三个操作数各自的不可折叠 producer（`xor` 与 tid 派生值）、guard 谓词（已实测 `IDP.4A` 本身不带 `@P`，由 `SEL` 事后选择结果）、加宽 kernel 签名（P1-1 模板轴）、目的与累加器重叠（`d == c`）、双条与四条 `dp4a` 累加器串联（`chain_depth_2`/`chain_depth_4`）、累加器起点为立即数的链（`chain_from_imm`）、两条独立 `dp4a` 经 `xor` 汇聚（`parallel_2`，防 O3 消除踩坑）、有符号立即数边界模式、间接 producer 与双立即数的组合探针。

## 入口与产物

- `suite_spec.py`：本指令独有的合法矩阵、上下文扩展、阴性探针和目标 SASS matcher（`IDP.4A`）。
- `suite_runtime.py`：本目录自包含的 manifest、编译、反汇编、归属和规则输出实现（原样拷贝自共享模板）。
- `generate_cases.py` / `validate_generated.py` / `check_cases.py` / `analyze_mapping_rules.py` / `check_negative_probes.py`：与 `01_tcgen05`/`02_tma` 套件同构的五个入口。
- `factors.json`：由生成器同步写出的机器可读因素和覆盖范围。
- `validation/`：适合提交仓库的紧凑验证摘要；`results/` 保存完整证据（Git 忽略）。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、全部 case 完成 `IDP.4A` 归属（`chain_depth_2`/`chain_depth_4`/`parallel_2` 分别归属 2/4/2 条实例）、且全部阴性探针被拒绝并匹配登记的诊断子串时才通过。该 PASS 证明静态实验闭环，不证明点积累加的数值正确性、饱和行为或 lane 顺序——这些留给运行时 oracle（见族文档 `STATIC_ONLY` 边界声明）。

## 已知与规范阅读冲突的实测结论

- `dp4a` 没有 `.sat` 修饰符（`Illegal modifier '.sat' for instruction 'dp4a'`），尽管它是 INT8 推理里常与饱和联系在一起的指令；PTX 语法层没有暴露饱和开关。
- 立即数在 `b` 槽与 `c` 槽的编译器路由不对称：`b` 为立即数时 O3 下用 `UR`（`IDP.4A.U8.U8 R9, R2, UR6, R5`），`c` 为立即数时 O3 下仍是 GPR（`IDP.4A.U8.U8 R9, R2, R5, R9`）——这是编译器实现细节，不是 ISA 强制约束，已如实记录而非归纳成规则。

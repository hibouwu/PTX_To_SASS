# `fma` (F32/F64) Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：20 个 syntax + 77 个 expanded case 于 O0–O3 共 388 次编译、反汇编与 `FFMA`/`DFMA` 归属全部通过；10 个负向探针全部按预期拒绝且诊断子串精确匹配）

## 目标

本目录用与 `02_tma`/`01_tcgen05` 相同的静态证据结构研究 `fma`（F32/F64 fused multiply-add）：有限合法语法矩阵、受控上下文变化、O0–O3 编译、带机器编码的反汇编、目标指令归属、正向/逆向规则候选及预期拒绝边界。运行时数值语义（舍入结果是否 bit-exact）不属于本套件的通过条件。

本目录是独立、自包含的实验套件，不导入其他指令目录或跨指令公共脚本；`suite_spec.py` 冻结本指令专用因素、case、阴性边界和 SASS matcher，`suite_runtime.py` 只服务本目录的生成、编译、归属与分析入口。

## 一键运行

```bash
cd PTX_SASS_mapping/06_cuda_core_fp/fma/thor_ptx90
./check_all.sh 8
```

结果目录需要放在大容量磁盘时，把第二个参数指定为独立路径：

```bash
./check_all.sh 8 /xplorer/shijy/fp-results/fma
```

## 实测映射摘要（详见族级 [`实验设计.md`](../../实验设计.md)）

- `fma` **没有**默认舍入模式：`rnd` 必须显式给出，省略即被拒绝（`Rounding modifier required for instruction 'fma'`）——这与 `add`/`sub`/`mul`（省略即默认 `.rn`）不同。
- `.rn` 不进 SASS 助记符；`.rz`/`.rm`/`.rp` 分别追加 `.RZ`/`.RM`/`.RP`。
- `.ftz`、`.sat` 只在 `.f32` 合法，`.f64` 上两者都被拒绝（各自独立诊断）。四档 `rnd` 与 `.ftz`/`.sat` 自由组合（`FFMA.FTZ.SAT`、`FFMA.RP.FTZ` 等）。
- PTX 语法**不允许**在 `fma` 操作数位直接写 `-%reg`/`|%reg|`（`Operand negation not allowed for instruction 'fma'`）；但一条独立的 `neg.f32`/`abs.f32` 生产者指令会被折叠进消费它的 `FFMA`/`DFMA` 源修饰符（`-Ra`/`|Ra|`），这是唯一能产生该效果的路径。
- 修饰符拼写顺序不是规范化的：`fma.f32.rn`、`fma.ftz.rn.f32`、`fma.sat.rn.f32` 都能通过并产生与规范拼写相同的 SASS——一个被校准推翻的假设（P0-2 补集抽样发现）。
- `fma.rn.f16`/`fma.rn.bf16`（打包半精度）在本 opcode 目录下**确实合法**（`HFMA2`/`HFMA2.BF16_V2`），只是不落在本套件的 `FFMA`/`DFMA` target_patterns 内——不能当作本目录的负向锚点，已改记为设计文档中的发现。
- 带 guard 谓词（`@%p fma...`）在 O0–O3 全部被 if-conversion 成无条件 `FFMA`/`DFMA` + `FSEL`/`DSEL` 选择，**从不**以 `@P FFMA` 字面形式出现——与 TMA 的 `UTMALDG` 谓词落地方式不同（后者有真实副作用，前者是纯算术，可以安全地无条件求值）。

## 语法矩阵摘要

- syntax（20 case）：`type`(f32/f64) × `rnd`(rn/rz/rm/rp) × `ftz`(仅 f32) × `sat`(仅 f32) 的合法组合全笛卡尔积，全寄存器操作数。
- expanded（77 case，含 syntax 全部复用为 `context=baseline`）追加：
  - 操作数类轴：`type` × 源槽(a/b/c) × 立即数取值(`0.0`/`1.0`/`-1.0`/`0.5`/最小非规格化数/最大规格化数) = 36 case；
  - neg/abs 折叠轴：`type` × (`neg_a`/`abs_a`/`neg_abs_a`) = 6 case；
  - 不可折叠 producer 轴：`type` × (tid 派生地址 / 二级指针间接) = 4 case（P1-2）；
  - 依赖链轴：`type` × (深度 2/4 依赖链、深度 2 并行链) = 6 case；
  - guard 谓词、加宽 kernel 签名（P1-1）各 `type` 一份 = 4 case；
  - 拼写变体（`fma.f32.rn`）1 case。

## 负向探针（10 条，全部登记 `expected_diagnostic` 并实测匹配）

| 探针 | 诊断 |
|---|---|
| `no_rounding_f32` | `Rounding modifier required for instruction 'fma'` |
| `ftz_f64` | `Illegal modifier '.ftz' for instruction 'fma'` |
| `sat_f64` | `Illegal modifier '.sat' for instruction 'fma'` |
| `integer_type`（`fma.rn.s32`） | `Unexpected instruction types specified for 'fma'` |
| `direct_operand_negation`（`-%a`） | `Operand negation not allowed for instruction 'fma'` |
| `arity_missing_operand`（3 操作数） | `Arguments mismatch for instruction 'fma'` |
| `type_mismatch_f64_operand_in_f32` | `Arguments mismatch for instruction 'fma'` |
| `approx_not_a_rounding_mode`（`fma.approx.f32`） | `Rounding modifier required for instruction 'fma'` |
| `double_rounding_modifier`（补集抽样，`fma.rn.rz.f32`） | `Multiple rounding modifiers specified` |
| `missing_type_suffix`（补集抽样，`fma.rn` 无类型） | `Unexpected instruction types specified for 'fma'` |

后两条是 P0-2 要求的"假定合法面之外"补集抽样：预先不假设它们合法或非法，先探针取真实诊断再登记，均确认拒绝。

## 基线零命中检查

脚手架（去掉 `fma` 目标行、只保留 `LDC`/`LDG`/`STG` 的同一 kernel）在 O0–O3 全部编译，`FFMA`/`DFMA` 命中数为零，之后才冻结本 spec。消费者统一为直接 `st.global`（不用 `xor`/`add` 汇聚），避免撞上 `FADD`/`LOP3` 造成归属污染。

## 入口与产物

- `suite_spec.py`：本指令独有的合法矩阵、上下文扩展、阴性探针和目标 SASS matcher（`FFMA`/`DFMA`）。
- `suite_runtime.py`：本目录自包含的 manifest、编译、反汇编、归属和规则输出实现（`family="fp"` 原样复制自共享模板）。
- `generate_cases.py` / `validate_generated.py` / `check_cases.py` / `analyze_mapping_rules.py` / `check_negative_probes.py`：与 `cp.async.bulk.tensor` 套件同构的五个入口。
- `factors.json`：由生成器同步写出的机器可读因素和覆盖范围。
- `validation/`：适合提交仓库的紧凑验证摘要；`results/` 保存完整证据（Git 忽略）。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、全部 case 完成 `FFMA`/`DFMA` 归属、且全部阴性探针被拒绝并匹配登记的诊断子串时才通过。该 PASS 证明静态实验闭环，不证明舍入结果的 bit-exact 正确性——数值 oracle 显式排除在 `STATIC_ONLY` 范围之外。

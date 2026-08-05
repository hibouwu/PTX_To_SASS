# `fence` Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：16 个 syntax + 29 个 expanded case 于 O0–O3 共 180 次编译、反汇编与 `MEMBAR`/`ERRBAR`/`CCTL.IVALL` 归属全部通过；9 个负向探针（6 条诊断锚定 + 3 条补集抽样）全部按预期拒绝且诊断子串匹配；脚手架基线零命中检查 O0–O3 全部为 0）

## 目标

本目录用与 `01_tcgen05`/`02_tma` 各指令套件相同的静态证据结构研究 `fence`：有限合法语法矩阵、受控上下文变化、O0–O3 编译、带机器编码的反汇编、目标指令归属、正向/逆向规则候选及预期拒绝边界。运行时可见性/顺序语义（litmus oracle）不属于本套件的通过条件，是族 README 完成门槛里显式排除的部分。

本目录是独立、自包含的实验套件，不导入其他指令目录或跨指令公共脚本；`suite_spec.py` 冻结本指令专用因素、case、阴性边界和 SASS matcher，`suite_runtime.py` 只服务本目录的生成、编译、归属与分析入口。

## 一键运行

```bash
cd PTX_SASS_mapping/04_fence/fence/thor_ptx90
./check_all.sh 4
```

## 语法矩阵摘要（全部来自实测，非规范阅读）

`fence.{sem}.{scope}` 的合法 sem 集合实测为**四个**：`sc`、`acq_rel`、`acquire`、`release`（后两个是本次校准推翻的假设——常见资料只强调 `sc`/`acq_rel` 组合，`acquire`/`release` 单独使用同样合法且各自产生独立可归属的 SASS），scope 集合为 `cta`/`cluster`/`gpu`/`sys`，4×4 全部 16 种组合编译通过：

- scope 轴在 SASS 层坍缩：`cluster` 与 `gpu` 对每个 sem 都逐位相同（scope 降级，而非编译期拒绝）；
- sem 轴可分解：`release` 部分贡献 `MEMBAR.{SC,ALL}.<scope>`（scope>cta 时再加 `ERRBAR`+`CGAERRBAR`），`acquire` 部分贡献 `CCTL.IVALL`（cta 时为空）；`sc` = SC 变体 release 部分 + acquire 部分，`acq_rel` = ALL 变体 release 部分 + acquire 部分；
- `fence.acquire.cta` 归属为零条目标指令（D 类，`empty_target_allowed` 按坐标放行）；
- 省略 sem 的简写 `fence.<scope>;` 合法，且与 `fence.acq_rel.<scope>;` 逐位相同（默认 sem 是 `acq_rel`，不是 `sc`——按规范直觉最容易猜错的一点）。

expanded 追加上下文轴：sem 简写拼写变体、fence 前后 global/shared/atomic 访存组合、双 fence 相邻（同 scope / 不同 scope / release+acquire 互补对，均已证不合并不去重，互补对之和恰好等于对应的单条 `acq_rel`）、guard 谓词、在飞深度 2/4（P0-1 控制位轴，本配置下未观测到编码变化）、加宽 kernel 签名（P1-1 模板轴）。

## 入口与产物

- `suite_spec.py`：本指令独有的合法矩阵、上下文扩展、阴性探针和目标 SASS matcher（`MEMBAR`/`ERRBAR`/`CCTL.IVALL`；`ERRBAR` 作为子串同时命中 `CGAERRBAR`，这是有意为之，因为二者总是作为同一条 fence lowering 序列的成员一起出现）。
- `suite_runtime.py`：本目录自包含的 manifest、编译、反汇编、归属和规则输出实现（`00_shared/templates/suite_runtime.py` 原样复制）。
- `generate_cases.py` / `validate_generated.py` / `check_cases.py` / `analyze_mapping_rules.py` / `check_negative_probes.py`：与既有套件同构的五个入口。
- `factors.json`：由生成器同步写出的机器可读因素和覆盖范围。
- `validation/`：适合提交仓库的紧凑验证摘要；`results/` 保存完整证据（Git 忽略）。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、全部 case 完成 `MEMBAR`/`ERRBAR`/`CCTL.IVALL` 归属（或落在登记的零指令坐标）、且全部阴性探针被拒绝并匹配登记的诊断子串时才通过。该 PASS 证明静态实验闭环：编译器为每种 sem×scope 组合选择了哪些指令、组合是否合并——不证明这些指令在实机上真正产生了声称的可见性或顺序效应。

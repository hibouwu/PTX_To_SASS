# `cp.async.bulk.tensor` Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：42 个 syntax + 52 个 expanded case 于 O0–O3 共 376 次编译、反汇编与 `UTMALDG`/`UTMASTG` 归属全部通过；12 个负向探针全部按预期拒绝且诊断子串匹配）

## 目标

本目录用与 `01_tcgen05` 各指令套件相同的静态证据结构研究 `cp.async.bulk.tensor`：有限合法语法矩阵、受控上下文变化、O0–O3 编译、带机器编码的反汇编、目标指令归属、正向/逆向规则候选及预期拒绝边界。运行时语义不属于本套件的通过条件。

本目录是独立、自包含的实验套件，不导入其他指令目录或跨指令公共脚本；`suite_spec.py` 冻结本指令专用因素、case、阴性边界和 SASS matcher，`suite_runtime.py` 只服务本目录的生成、编译、归属与分析入口。

相对 tcgen05 套件的两处结构增强：

1. `Spec.ptx_opcode` 与短名分离，manifest 记录完整 PTX opcode；
2. 负向探针可登记 `expected_diagnostic` 子串，拒绝必须携带其声称要测的那条约束的诊断信息才算通过（回应 tcgen05 对抗式审查 P0-2 的"拒绝不等于定位"）。

## 一键运行

```bash
cd PTX_SASS_mapping/02_tma/cp.async.bulk.tensor/thor_ptx90
./check_all.sh 8
```

结果目录需要放在大容量磁盘时，把第二个参数指定为独立路径：

```bash
./check_all.sh 8 /xplorer/shijy/tma-results/bulk_tensor
```

## 语法矩阵摘要

- load（`.mbarrier::complete_tx::bytes` 完成）：`tile` rank 1d–5d × dst `shared::cta`/`shared::cluster`、`tile::gather4`（仅 2d）、`im2col`/`im2col::w`/`im2col::w::128`（3d–5d）、`.multicast::cluster`（仅 cluster dst）、`.cta_group::1/::2`、`.L2::cache_hint`，以及五个已校准的修饰符组合；
- store（`.bulk_group` 完成）：`tile` 1d–5d、`tile::scatter4`（仅 2d）、`im2col_no_offs`（3d–5d）、`.L2::cache_hint`；
- expanded 追加上下文轴：坐标/tensormap/mbarrier 的 producer 来源、guard 谓词、在飞条数 2/4（P0-1 控制位轴）、`cta_group` 后置拼写变体、加宽 kernel 签名（P1-1 模板轴）、store 侧 wait 距离与双 group `wait_group 1`。

## 入口与产物

- `suite_spec.py`：本指令独有的合法矩阵、上下文扩展、阴性探针和目标 SASS matcher（`UTMALDG`/`UTMASTG`）。
- `suite_runtime.py`：本目录自包含的 manifest、编译、反汇编、归属和规则输出实现。
- `generate_cases.py` / `validate_generated.py` / `check_cases.py` / `analyze_mapping_rules.py` / `check_negative_probes.py`：与 tcgen05 套件同构的五个入口。
- `factors.json`：由生成器同步写出的机器可读因素和覆盖范围。
- `validation/`：适合提交仓库的紧凑验证摘要；`results/` 保存完整证据（Git 忽略）。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、全部 case 完成 `UTMALDG`/`UTMASTG` 归属、且全部阴性探针被拒绝并匹配登记的诊断子串时才通过。该 PASS 证明静态实验闭环，不证明实机搬运数据、mbarrier 完成或 bulk group 排序语义。

# `membar` Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：3 个 syntax + 11 个 expanded case 于 O0–O3 共 56 次编译、反汇编与 `MEMBAR`/`ERRBAR`/`CCTL.IVALL` 归属全部通过；6 个负向探针（4 条诊断锚定 + 2 条补集抽样）全部按预期拒绝且诊断子串匹配；脚手架基线零命中检查沿用 `../fence/thor_ptx90` 的同构验证）

## 目标

本目录用与 `fence/thor_ptx90` 相同的静态证据结构研究传统 `membar`，并把"`membar` 是 `fence.sc.*` 的严格子集"这一论断落到独立可复现的证据上，而不是只在文档里断言。运行时可见性/顺序语义不属于本套件的通过条件。

`membar` 的合法语法比 `fence` 窄得多：只有三档传统 level（`cta`/`gl`/`sys`，**没有** `cluster`，也**没有** `gpu` 拼写——`gpu` 是 `fence` 的新式记号，`membar` 上非法），且没有 sem 轴（`.sc`/`.acq_rel`/`.acquire`/`.release` 全部非法）。因此本套件规模明显小于 `fence`，`check_all.sh` 默认作业数与产物结构保持一致以便交叉核对。

## 一键运行

```bash
cd PTX_SASS_mapping/04_fence/membar/thor_ptx90
./check_all.sh 4
```

## 实测别名关系（本套件的核心结论）

| `membar` | 逐位相同于 | SASS |
|---|---|---|
| `membar.cta` | `fence.sc.cta` | `MEMBAR.SC.CTA` |
| `membar.gl` | `fence.sc.gpu` / `fence.sc.cluster` | `MEMBAR.SC.GPU`+`ERRBAR`+`CGAERRBAR`+`CCTL.IVALL` |
| `membar.sys` | `fence.sc.sys` | `MEMBAR.SC.SYS`+`ERRBAR`+`CGAERRBAR`+`CCTL.IVALL` |

expanded 追加与 `fence` 同构的上下文轴（前后 global/shared 访存、双 membar 相邻的合并/去重观察、guard、在飞深度、加宽签名），供跨套件差分核对。

## 入口与产物

- `suite_spec.py`：本指令独有的合法矩阵、上下文扩展、阴性探针和目标 SASS matcher。
- `suite_runtime.py`：`00_shared/templates/suite_runtime.py` 原样复制。
- `generate_cases.py` / `validate_generated.py` / `check_cases.py` / `analyze_mapping_rules.py` / `check_negative_probes.py`：与既有套件同构的五个入口。
- `validation/`：适合提交仓库的紧凑验证摘要；`results/` 保存完整证据（Git 忽略）。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、全部 case 完成目标指令归属、且全部阴性探针被拒绝并匹配登记的诊断子串时才通过。该 PASS 证明静态实验闭环，不证明这些指令在实机上真正产生了声称的可见性或顺序效应。

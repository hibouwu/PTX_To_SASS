# `mbarrier.arrive` Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：15 个 syntax + 24 个 expanded case 于 O0–O3 共 156 次编译、反汇编与 `SYNCS.ARRIVE.TRANS64` 归属全部通过；7 个负向探针全部按预期拒绝且诊断子串匹配）

## 目标

本目录用与 `01_tcgen05`/`02_tma` 各指令套件相同的静态证据结构研究 `mbarrier.arrive`：有限合法语法矩阵、受控上下文变化、O0–O3 编译、带机器编码的反汇编、目标指令归属、正向/逆向规则候选及预期拒绝边界。运行时语义（barrier 到达计数、phase 翻转、跨 CTA 可见性）不属于本套件的通过条件。

本目录是独立、自包含的实验套件，不导入其他指令目录或跨指令公共脚本；`suite_spec.py` 冻结本指令专用因素、case、阴性边界和 SASS matcher，`suite_runtime.py` 是 `00_shared/templates/suite_runtime.py` 的逐字节副本（`family="mbarrier"`），只服务本目录的生成、编译、归属与分析入口。

## 一键运行

```bash
cd PTX_SASS_mapping/03_mbarrier/mbarrier.arrive/thor_ptx90
./check_all.sh 4
```

结果目录需要放在大容量磁盘时，把第二个参数指定为独立路径：

```bash
./check_all.sh 4 /xplorer/shijy/mbarrier-results/arrive
```

## 语法矩阵摘要

- `sem`（`.release`/`.relaxed`）× `scope`（`.cta`/`.cluster`）满因子：核心 `SYNCS.ARRIVE.TRANS64...` 恒为 1 条，但 `sem=.release ∧ scope=.cluster` 会在其前插入固定四指令前导序列（`MEMBAR.ALL.CTA`+`MEMBAR.ALL.GPU`+`ERRBAR`+`CGAERRBAR`），`.relaxed` 无论 `scope` 为何都不触发；
- 地址空间拼写等价性：`.shared`、`.shared::cta`、无限定符（真正的 64 位 generic 地址，经 `mov.u64` 直接取得）三者 SASS 相同；
- `.shared::cluster`（remote/DSMEM）地址触发正交的 `.RED` 后缀，且强制目的操作数为 sink `_`（负向探针 `remote_real_token`）；`.RED` 触发条件与前导序列触发条件相互独立，用 `scope=.cta` 配 remote 地址的补集抽样 case 验证解耦；
- count 操作数缺省/立即数/寄存器：立即数与寄存器 SASS 相同（`.ART0`），缺省为 `.A1T0`；
- token 消费方式（`st.global` 落地 / `_` 丢弃）不影响指令是否发射（副作用指令），只影响目的寄存器是否为 `RZ`；
- `.noComplete`：要求显式 count（立即数/寄存器同形皆已覆盖），产生 `.TMASK.ART0`；与 `.cluster` scope 组合被 ptxas 拒绝（负向探针 `nocomplete_cluster_scope`）；
- expanded 追加上下文轴：地址/count 的 producer 间接来源（算术派生地址、`ld.global` 装载的 count）、guard 谓词、在飞多 barrier（2/4 条独立 mbarrier 背靠背 arrive，P0-1 控制位轴）、加宽 kernel 签名（P1-1 模板轴，已校准为对本指令无扰动的空结果）、`sem`/`scope` 全部省略的默认拼写、以及两个 P0-2 发现渠道 case（寄存器来源的运行时零计数、`.cta` scope 配 remote 地址）。

## 入口与产物

- `suite_spec.py`：本指令独有的合法矩阵、上下文扩展、阴性探针和目标 SASS matcher（`SYNCS.ARRIVE.TRANS64`）。
- `suite_runtime.py`：`00_shared/templates/suite_runtime.py` 的原样副本，提供 manifest、编译、反汇编、归属和规则输出实现。
- `generate_cases.py` / `validate_generated.py` / `check_cases.py` / `analyze_mapping_rules.py` / `check_negative_probes.py`：与 tcgen05/TMA 套件同构的五个入口。
- `factors.json`：由生成器同步写出的机器可读因素和覆盖范围。
- `validation/`：适合提交仓库的紧凑验证摘要；`results/` 保存完整证据（Git 忽略）。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、全部 case 完成 `SYNCS.ARRIVE.TRANS64` 归属、且全部阴性探针被拒绝并匹配登记的诊断子串时才通过。该 PASS 证明静态实验闭环，不证明实机 barrier 到达计数、phase/parity 翻转或跨 CTA 可见性语义；族级结构分类、9 个 opcode 的完整校准记录与 STATIC_ONLY 边界见 [`../实验设计.md`](../实验设计.md)。

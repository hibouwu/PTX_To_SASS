# `brx.idx` Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：18 个 syntax + 25 个 expanded case 于 O0–O3 共 172 次编译、反汇编与 `BRX`/`BRXU` 归属全部通过；7 个负向探针全部按预期拒绝且诊断子串匹配）

## 目标

本目录用与 `01_tcgen05`/`02_tma` 各指令套件相同的静态证据结构研究 `brx.idx`：有限合法语法矩阵、受控上下文变化、O0–O3 编译、带机器编码的反汇编、目标指令归属、正向/逆向规则候选及预期拒绝边界。运行时语义不属于本套件的通过条件。

本目录是独立、自包含的实验套件，不导入其他指令目录或跨指令公共脚本；`suite_spec.py` 冻结本指令专用因素、case、阴性边界和 SASS matcher，`suite_runtime.py` 只服务本目录的生成、编译、归属与分析入口。

`brx.idx` 被选为 `08_control_flow` 族的旗舰 opcode，原因是它的 SASS 助记符 `BRX`/`BRXU` 从不与 kernel 尾部恒有的 `EXIT` + 自跳 `BRA` 收尾结构发生子串冲突——族内其余四个 opcode（`bra`/`call`/`ret`/`exit`）全部落在 `BRA`/`EXIT`/`CALL`/`RET` 这些与尾部结构或彼此重叠的助记符上，逐指令归属需要块结构而非子串匹配，因此不适合作为可用子串匹配验证的旗舰（详见 `../../实验设计.md`）。

## 一键运行

```bash
cd PTX_SASS_mapping/08_control_flow/brx.idx/thor_ptx90
./check_all.sh 8
```

结果目录需要放在大容量磁盘时，把第二个参数指定为独立路径：

```bash
./check_all.sh 8 /xplorer/shijy/cf-results/brx_idx
```

## 语法矩阵摘要

- **baseline 全因子**（`syntax_cases`，18 例）：`target_count`∈{2,3,4} × `index_source`∈{`immediate`（常量 0）,`register_uniform`（kernel 参数按位 `and` 掩码，warp 一致）,`laneid`（`%laneid` 按位 `and` 掩码，天然 divergent）} × `merge`∈{`shared`（各目标块 `bra.uni` 汇合到共同 `DONE`）,`separate`（各目标块各自 `ret`）}；每个目标块用不同立即数 + 不同 `st.global` 偏移区分副作用，防止 O3 合并块。
- **expanded 追加上下文轴**（另 7 例）：`guard_uniform`/`guard_divergent`（`@%p brx.idx`，一致谓词不触发重汇聚，divergent 谓词触发 `BSSY.RECONVERGENT`/`BSYNC.RECONVERGENT`，这是本族 P0-1 对应物的直接证据）、`index_indirect`（索引从全局内存指针间接装载，P1-2）、`template_wide`（加宽/打乱参数签名，P1-1）、`duplicate_target`（`.branchtargets` 列表重复引用同一物理块，已校准合法，一个发现）、`single_target`（单目标 `.branchtargets`，已校准合法边界）、`double_chain`（同一 kernel 内两个独立 `.branchtargets`/`brx.idx` 对，序列级组合，P0-3 对应物）。

## 已校准的合法面 → SASS 现象对照

| 现象 | 结论 |
|---|---|
| O0 lowering | 恒为 `BRX Rd -off (*"BRANCH_TARGETS ..."*)`（GPR，从不折叠、从不预测化） |
| O1–O3，索引 warp-uniform | `BRXU URd (*"BRANCH_TARGETS ..."*)`（UR，一致值数据通路） |
| O1–O3，索引 tid/laneid 派生 | 仍为 `BRX`（GPR）；uniform 值分析对 `and.b32` 保持一致性，对 `rem.u32` **不**保持（见下方"意外发现"） |
| 索引为编译期常量、越界 | O0 接受、零静态诊断（真实 BRX，运行时行为未检查/未定义）；O3 整体折叠为裸 `EXIT`（激进 UB 假设优化，非语义保证） |
| 索引为编译期常量、在界 | O1 起完全折叠（`empty_target_allowed` 按坐标放行） |
| `.branchtargets` 重复引用同一物理块 / 单目标列表 | 编译合法；因目的地与索引值无关，O1 起同样完全折叠 |
| `@%p brx.idx` | 合法语法；从不生成预测化 `BRX`，恒重构为"skip-branch + 无条件 BRX"；guard 谓词一致时无重汇聚簿记，guard 谓词 divergent 时套 `BSSY.RECONVERGENT`/`BSYNC.RECONVERGENT`（观测到嵌套的 `BSSY.RELIABLE`/`BSYNC.RELIABLE` 第二层，见族级设计文档） |

完整发现记录、诊断文本与对抗式审查缺口对应见 [`../../实验设计.md`](../../实验设计.md)。

## 入口与产物

- `suite_spec.py`：本指令独有的合法矩阵、上下文扩展、阴性探针和目标 SASS matcher（`("BRX",)`——`BRXU` 因含 `BRX` 子串同时命中，无需单独登记）。
- `suite_runtime.py`：本目录自包含的 manifest、编译、反汇编、归属和规则输出实现（原样复制自 `00_shared/templates/suite_runtime.py`，`family="cf"`）。
- `generate_cases.py` / `validate_generated.py` / `check_cases.py` / `analyze_mapping_rules.py` / `check_negative_probes.py`：与 tcgen05/TMA 套件同构的五个入口。
- `factors.json`：由生成器同步写出的机器可读因素和覆盖范围。
- `validation/`：适合提交仓库的紧凑验证摘要；`results/` 保存完整证据（Git 忽略）。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、非折叠 case 完成 `BRX`/`BRXU` 归属、折叠 case 按坐标放行 `empty_target_allowed`、且全部阴性探针被拒绝并匹配登记的诊断子串时才通过。该 PASS 证明静态实验闭环，不证明实机跳转目标选择、越界索引的运行时行为或 warp 收敛正确性。

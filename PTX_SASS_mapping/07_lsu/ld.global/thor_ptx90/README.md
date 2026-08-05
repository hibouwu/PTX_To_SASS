# `ld.global` Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：70 个 syntax + 79 个 expanded case 于 O0–O3 共 596 次编译、反汇编与 `LDG` 归属全部通过，`missing_target_count=0`；10 个负向探针全部按预期拒绝且诊断子串精确匹配；规则挖掘 316 正向记录 / 93 唯一逆向签名）

## 目标

本目录用与 `01_tcgen05`/`02_tma` 各指令套件相同的静态证据结构研究 `ld.global`：有限合法语法矩阵、受控上下文变化、O0–O3 编译、带机器编码的反汇编、目标指令归属、正向/逆向规则候选及预期拒绝边界。运行时语义不属于本套件的通过条件。

本目录是独立、自包含的实验套件，不导入其他指令目录或跨指令公共脚本；`suite_spec.py` 冻结本指令专用因素、case、阴性边界和 SASS matcher，`suite_runtime.py` 只服务本目录的生成、编译、归属与分析入口（`family="lsu"`，与其余 `07_lsu/*` 未来套件共享同一 runtime 拷贝，但目录之间互不依赖）。

## 一键运行

```bash
cd PTX_SASS_mapping/07_lsu/ld.global/thor_ptx90
./check_all.sh 8
```

结果目录需要放在大容量磁盘时，把第二个参数指定为独立路径：

```bash
./check_all.sh 8 /xplorer/shijy/lsu-results/ld_global
```

## 头条校准结论（详见族级 [`实验设计.md`](../../实验设计.md)）

- weak 形态的 cache-op 与显式内存序 scope 修饰符在本机上**共用同一个编码族**：`.ca`≡`relaxed.cta`≡`acquire.cta`→`STRONG.SM`，`.cg`≡`relaxed.{gpu,cluster}`≡`acquire.{gpu,cluster}`→`STRONG.GPU`，`.cv`≡`relaxed.sys`≡`acquire.sys`≡`.volatile`→`STRONG.SYS`（两条编码字逐位相同，非仅助记符相同）；`.cs`→`EF`、`.lu`→`LU` 是唯一不落入别名族的两档。
- `relaxed` 与 `acquire` 在孤立单条 load 上编码逐字节相同，不插入 `MEMBAR`——语义区分在本层静态证据里不可见。
- `ld.global.nc` 的 `.ca`/`.cg` 与无 cache-op 的 `nc` 逐位相同（`LDG.E.CONSTANT`），cache-op 在 nc 路径上被吸收。
- 寄存器+偏移只在 O1–O3 折进 `LDG` 自身的操作数，且仅限有符号 24 位窗口 `[-0x800000, 0x7fffff]`；O0 恒用 `IADD3` 预计算地址；越界一步时编译器用一次额外的 `(U)IADD3` 把基址移位再取边界立即数拼出等价地址。
- 标量 `.b128` **合法**（`STG.E.128`，与 `.v4.b32`/`.v2.b64` 同宽度类）——这推翻了"标量 128-bit 宽度非法"的直觉假设；真正非法的向量宽度是 `.v3`。
- `ldu.global.*` 语法合法但**没有独立 SASS 形态**：与同宽度 `ld.global` 产生逐位相同的 `LDG.E[.width]` 编码。

## 语法矩阵摘要

- `syntax_cases`（70 例）：宽度（`b8/b16/b32/b64/v2.b32/v4.b32`）× cache-op（无/`.ca`/`.cg`/`.cs`/`.lu`/`.cv`）全笛卡尔积（36 例）；`relaxed`/`acquire` × `cta/cluster/gpu/sys`（b32，8 例）+ `relaxed.gpu`/`acquire.gpu` 跨宽度抽样（5 例）；`.volatile` × 全宽度（6 例）；`.weak` 显式拼写等价性（1 例）；`ld.global.nc` 若干形态（5 例）；地址形态轴（寄存器/正负小偏移/±0x7fffff 边界内外，7 例）+ 具名符号（1 例）；额外宽度点 `.b128`（2 例）。
- `expanded_cases`（79 例 = 上述 70 例 + 9 个上下文 case）：指针的指针（P1-2 间接 producer）、同址双载（不同 cache-op）、相邻可能别名 store→load、guard 谓词、`template_wide`（P1-1）、`inflight_depth_{2,4}`（P0-1 scoreboard 轴）、`scope_plus_inflight_2`（已校准双修饰符组合的序列化）、`consume_distance_far`（消费距离轴）。

## 入口与产物

- `suite_spec.py`：本指令独有的合法矩阵、上下文扩展、阴性探针和目标 SASS matcher（`target_patterns=("LDG",)`）。
- `suite_runtime.py`：本目录自包含的 manifest、编译、反汇编、归属和规则输出实现（`00_shared/templates/suite_runtime.py` 原样拷贝）。
- `generate_cases.py` / `validate_generated.py` / `check_cases.py` / `analyze_mapping_rules.py` / `check_negative_probes.py`：与 tcgen05/TMA 套件同构的五个入口。
- `factors.json`：由生成器同步写出的机器可读因素和覆盖范围。
- `validation/`：适合提交仓库的紧凑验证摘要；`results/` 保存完整证据（Git 忽略）。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、全部 case 完成 `LDG` 归属、且全部阴性探针被拒绝并匹配登记的诊断子串时才通过。基线零命中检查已执行：脚手架（参数装载 + `mov`/`st.global` 落地，无 `ld.global`）在 O0–O3 下 `LDG` 命中数为零。该 PASS 证明静态实验闭环，不证明实机数据搬运、内存序可见性或 cache-op 提示的真实效果。

## 已知局限 / 留待后续

- `.b128`、`.v2.b64` 只做了基线合法性确认，未展开完整 cache-op 矩阵。
- `.mmio` 修饰符已发现存在但未展开校准表，只作为负向探针的补集抽样登记。
- generic 寻址（`cvta.global` + 裸 `ld`/`st` → `LD.E`/`ST.E`）已在族文档记录为独立助记符族，但**不计入本套件的 `LDG` 归属**（故意排除，避免把两族目标混进同一次统计）；留给未来单开对照 case 或独立子任务。

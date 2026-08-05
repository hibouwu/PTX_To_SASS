# `mov` thread-index special registers Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：24 个 syntax + 46 个 expanded case 于 O0–O3 共 280 次编译、反汇编与目标归属全部通过；9 个负向探针全部按预期拒绝且诊断子串匹配）

## 目标

本目录用与 `01_tcgen05`/`02_tma` 各指令套件相同的静态证据结构研究 `%tid.{x,y,z}` 与
`%ntid.{x,y,z}` 这两个 thread-index special register 组：通过 `mov.u32 %r, %sreg;`
读取，有限合法语法矩阵、受控消费者/上下文变化、O0–O3 编译、带机器编码的反汇编、目标指令
归属、正向/逆向规则候选及预期拒绝边界。运行时语义（`%tid`/`%ntid` 的实际数值）不属于本套件
的通过条件——`STATIC_ONLY`。

本目录是独立、自包含的实验套件，不导入其他指令目录或跨指令公共脚本；`suite_spec.py` 冻结
本组专用因素、case、阴性边界和 SASS matcher，`suite_runtime.py` 只服务本目录的生成、编译、
归属与分析入口。

本套件与其他族套件的一处结构差异：special register 家族没有独立助记符（消费者永远是
`mov`），语义差异体现在**特殊寄存器操作数**而非助记符，因此 `target_patterns` 匹配的是
SASS 操作数文本（`SR_TID.X/Y/Z`、`c[0x0][0x360/0x364/0x368]`）而非指令助记符前缀；已用
脚手架零命中检查确认这组模式不会误命中任何 boilerplate 指令。

## 一键运行

```bash
cd PTX_SASS_mapping/09_special_reg/thread-index/thor_ptx90
./check_all.sh 8
```

结果目录需要放在大容量磁盘时，把第二个参数指定为独立路径：

```bash
./check_all.sh 8 /xplorer/shijy/sreg-results/thread-index
```

## 语法矩阵摘要

- `SF.kind`（`tid`/`ntid`）× `SF.dim`（`x`/`y`/`z`）× `SF.consumer`（`store`/`address`/
  `predicate`/`multi_use`）= 24 个 syntax case；
- expanded 追加上下文轴：`.reqntid` 有无（P1-1 隐藏全局变量轴，**实测：不折叠**）、双读
  复用（同一 sreg 两条独立 PTX `mov`，**实测：`%tid` 在 O1+ 被 CSE 成单条 `S2R`，
  `%ntid` 从不合并，O1+ 仍是两条常量库读取，只是其中一条会挑成 `LDCU`）、加宽 kernel
  签名（P1-1 模板轴）、uniformity 操纵（`shfl.sync.idx` 广播消费——`%tid.x` 的
  `SHFL.IDX` 保留，`%ntid.x` 的 `SHFL.IDX` 被整条消除）、divergent branch 消费（确认
  producer 机制不随控制流分支改变）、`mov.v4.u32` 整向量读（按分量拆成
  `S2R`/`LDC` 序列，`.w` 分量恒被常量折叠、不产生任何指令）、`.r/.g/.b/.a` 拼写变体
  （确认与 `.x/.y/.z/.w` 同 SASS）。

完整的"寄存器→producer 类别"全表（47 个 special register，覆盖全部 8 个语义组）与
`%tid`/`%ctaid` 两组 manipulation check 结论见 [`../../实验设计.md`](../../实验设计.md)。

## 入口与产物

- `suite_spec.py`：本组独有的合法矩阵、上下文扩展、阴性探针和目标 SASS matcher。
- `suite_runtime.py`：本目录自包含的 manifest、编译、反汇编、归属和规则输出实现。
- `generate_cases.py` / `validate_generated.py` / `check_cases.py` /
  `analyze_mapping_rules.py` / `check_negative_probes.py`：与其他族套件同构的五个入口。
- `factors.json`：由生成器同步写出的机器可读因素和覆盖范围。
- `validation/`：适合提交仓库的紧凑验证摘要；`results/` 保存完整证据（Git 忽略）。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、全部 case 完成目标归属、且
全部阴性探针被拒绝并匹配登记的诊断子串时才通过。该 PASS 证明静态实验闭环，不证明
`%tid`/`%ntid` 在实机上的具体数值或跨线程一致性。

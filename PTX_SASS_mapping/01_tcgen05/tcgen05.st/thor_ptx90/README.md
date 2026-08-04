# `tcgen05.st` Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_READY`（生成器和检查流水线已建立；在 Thor 上运行 `check_all.sh` 后才能升级为已有映射证据）

## 目标

本目录用与 `tcgen05.mma/thor_ptx90` 相同的静态证据结构研究 `tcgen05.st`：有限合法语法矩阵、受控上下文变化、O0–O3 编译、带机器编码的反汇编、目标指令归属、正向/逆向规则候选及预期拒绝边界。运行时语义不属于本套件的通过条件。

本目录是独立、自包含的实验套件，不导入其他 tcgen05 指令目录或跨指令公共脚本；`suite_spec.py` 冻结本指令专用因素、case、阴性边界和 SASS matcher，`suite_runtime.py` 只服务本目录的生成、编译、归属与分析入口。

## 一键运行

```bash
cd PTX_SASS_mapping/01_tcgen05/tcgen05.st/thor_ptx90
./check_all.sh 4
```

若结果目录需要放在大容量磁盘，可把第二个参数指定为独立路径：

```bash
./check_all.sh 8 /xplorer/shijy/tcgen05-results/st
```

## 入口与产物

- `suite_spec.py`：本指令独有的合法矩阵、上下文扩展、阴性探针和目标 SASS matcher。
- `suite_runtime.py`：本目录自包含的 manifest、编译、反汇编、归属和规则输出实现。
- `generate_cases.py`：生成 `syntax` 或 `expanded` PTX 与 manifest。
- `validate_generated.py`：检查 case ID、源码哈希、目标标记和 manifest 一致性。
- `check_cases.py`：调用 CUDA 13 `ptxas` 进行 O0–O3 编译，再调用 `nvdisasm` 提取完整 SASS、目标操作和 128-bit 编码。
- `analyze_mapping_rules.py`：由 expanded manifest 和 attribution 生成正向记录与保守逆向候选。
- `check_negative_probes.py`：验证登记的非法语法或 qualifier 组合确实被拒绝。
- `factors.json`：由生成器同步写出的机器可读因素和覆盖范围。
- `validation/`：适合提交仓库的紧凑验证摘要；`results/` 保存完整证据。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、要求独立目标的 case 完成 SASS 归属、预登记的空 lowering 被显式记录且全部阴性探针按预期拒绝时才通过。该 PASS 证明静态实验闭环，不证明实机数值、完成、参与或资源生命周期语义。

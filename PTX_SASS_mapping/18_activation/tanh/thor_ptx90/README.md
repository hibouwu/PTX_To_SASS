# `tanh` Thor/PTX 9.0 静态映射实验

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：15 个 syntax + 25 个 expanded case 于 O0–O3 共 160 次
编译、反汇编与 `MUFU.TANH` 归属全部通过；10 个负向探针全部按预期拒绝且诊断子串匹配；基线零命中检查
先行通过）

## 目标

本目录用与 `01_tcgen05`/`02_tma` 各指令套件相同的静态证据结构研究 `tanh`：有限合法语法矩阵（dtype ×
consumer 全 factorial）、受控上下文变化（producer/guard/模板/在飞深度/拆 lane）、O0–O3 编译、带机器
编码的反汇编、目标指令归属、正向/逆向规则候选及预期拒绝边界。运行时语义（数值精度、特殊值）不属于
本套件的通过条件，见 [`../实验设计.md`](../实验设计.md) 的 `STATIC_ONLY` 声明。

本目录是独立、自包含的实验套件，不导入其他指令目录或跨指令公共脚本；`suite_spec.py` 冻结本指令专用
因素、case、阴性边界和 SASS matcher，`suite_runtime.py`（`family="act"`）原样复制自
[`00_shared/templates/suite_runtime.py`](../../../00_shared/templates/suite_runtime.py)。

## 一键运行

```bash
cd PTX_SASS_mapping/18_activation/tanh/thor_ptx90
./check_all.sh 4
```

结果目录需要放在大容量磁盘时，把第二个参数指定为独立路径：

```bash
./check_all.sh 4 /xplorer/shijy/act-results/tanh
```

## 语法矩阵摘要

- `SF.dtype`：`f32`/`f16`/`bf16`/`f16x2`/`bf16x2`（`tanh` 的全部合法 dtype，已实测；`.approx` 在全部
  dtype 上强制，`.rn`/`.ftz`/`.sat` 在全部 dtype 上非法）；
- `SF.consumer`：`direct`（落地）/`mul`（乘一个间接来源的同 dtype 操作数）/`cvt`（`f32` 降精度到
  `f16` 存储、`f16`/`bf16` 升精度到 `f32` 存储、`f16x2`/`bf16x2` 拆 lane 后各自升精度再求和存储——
  三种 consumer 在全部 dtype × O0–O3 上都实测**不与 `tanh` 融合**，`MUFU.TANH`/`MUFU.TANH.F16`/
  `MUFU.TANH.BF16` 始终作为独立指令出现）；
- `CTX.context`（expanded 独有）：`producer_indirect`（源操作数来自 `%tid.x` 派生值，P1-2 不可折叠
  前提）、`cvt_producer`（先 `cvt.rn.f16.f32` 再 `tanh.approx.f16`，对照直接 `f16` 加载）、
  `double_chain`（`tanh(tanh(x))` 两条独立 `MUFU.TANH` 背靠背）、`lane_asym`（`f16x2`/`bf16x2` 的两个
  lane 来自独立加载且都被下游消费，避免 O3 把拆 lane 序列 DCE 退化为单条标量 `MUFU`）、`guard`
  （谓词不落在 `MUFU.TANH` 上，ptxas 无条件计算后用 `FSEL` 选择）、`template_wide`（P1-1 模板轴）、
  `inflight_depth_2`/`inflight_depth_4`（P0-1 控制位轴）、`immediate_source`（发现：`MUFU.TANH` 接受
  立即数源操作数）。

## 入口与产物

- `suite_spec.py`：本指令独有的合法矩阵、上下文扩展、阴性探针和目标 SASS matcher（`MUFU.TANH`，子串
  匹配天然覆盖 `MUFU.TANH.F16`/`MUFU.TANH.BF16`）。
- `suite_runtime.py`：本目录自包含的 manifest、编译、反汇编、归属和规则输出实现（`family="act"`）。
- `generate_cases.py` / `validate_generated.py` / `check_cases.py` / `analyze_mapping_rules.py` /
  `check_negative_probes.py`：与既有套件同构的五个入口。
- `factors.json`：由生成器同步写出的机器可读因素和覆盖范围。
- `validation/`：适合提交仓库的紧凑验证摘要；`results/` 保存完整证据（Git 忽略）。

## 判定规则

`check_all.sh` 只有在全部合法 case 于 O0–O3 编译和反汇编成功、全部 case 完成 `MUFU.TANH` 归属、且全部
阴性探针被拒绝并匹配登记的诊断子串时才通过。该 PASS 证明静态实验闭环，不证明 `tanh` 的数值近似精度或
特殊值行为——见族级 `STATIC_ONLY` 声明。

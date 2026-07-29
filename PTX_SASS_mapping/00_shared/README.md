# 共享实验约定

这里存放 `PTX_SASS_mapping` 内部各指令族共同使用的协议，不承载任何指令族自己的实验结果。

## 独立性

`verification_num_mapping/` 的分类可用于确定目录名称和初始范围，但其 testcase、SASS、
verdict、runtime 记录和覆盖率都不是本实验的输入证据。需要引用背景材料时必须标为
`external_reference`，不能标为本实验的 observation。

## 推荐的族内结构

各族开始实施时按需创建以下内容，不提前创建空目录：

```text
<family>/
├── README.md
├── factors.yaml          # 精确水平、合法性约束和有界范围
├── cases/                # 本实验生成的 PTX 与 testcase manifest
├── witnesses/            # 每种 lowering 的最小复现
├── results/<env-id>/     # 原始产物、日志、fingerprint 和状态账本
└── notes/                # 人工归属、反例和待证假设
```

## 统一状态

| 状态 | 含义 |
|---|---|
| `NOT_STARTED` | 只有范围说明，尚未冻结因子模型 |
| `DESIGNED` | 已冻结本轮环境、因子水平、约束和停止条件 |
| `GENERATED` | testcase 已生成，尚未完成全部编译与观测 |
| `OBSERVED` | 产物账本完整，但候选尚未完成语义或归属验证 |
| `VALIDATED` | 本轮候选、反例、语义和覆盖报告均已完成 |
| `BLOCKED` | 存在设备、工具链、规范或归属阻塞，原因已记录 |

单个 testcase 必须落入互斥结果状态，例如：

```text
SPEC_ILLEGAL
TARGET_UNSUPPORTED
COMPILE_REJECTED
TARGET_ELIMINATED
DESIGN_NOT_REALIZED
ATTRIBUTION_UNKNOWN
OBSERVED_VARIANT
SEMANTIC_PASS
SEMANTIC_FAIL
```

## 统一观测层次

每个候选至少保留三种表示：

1. `exact`：原始机器码、控制字段、relocation 和完整物理寄存器。
2. `allocation`：规范化寄存器编号，但保留寄存器类别、寄存器对、predicate polarity
   和 operand slot。
3. `semantic`：按目标 effect slice 的 def-use/CFG 结构规范化。

删除、融合、展开、复制和无法归属不是普通 opcode 序列，而是独立 lowering 类别。

## 组合覆盖

- 单因素差分用于解释主效应，不用于筛掉后续组合因素。
- 所有因素都应进入受约束的组合覆盖。
- 对高风险因素簇做局部全因子或更高阶覆盖。
- 只完成 t-wise 覆盖时，结论只能写为 “t-wise 覆盖完成”。
- 只有穷举冻结后的有限输入空间，才能写为“相对于该输入空间完整”。

族目录可从 [族实验模板.md](族实验模板.md) 复制计划结构。


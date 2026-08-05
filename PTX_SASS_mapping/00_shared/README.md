# 共享实验约定

这里存放 `PTX_SASS_mapping` 内部各指令族共同使用的协议，不承载任何指令族自己的实验结果。

## 独立性

`verification_num_mapping/` 的分类可用于确定目录名称和初始范围，但其 testcase、SASS、verdict、runtime 记录和覆盖率都不是本实验的输入证据。需要引用背景材料时必须标为 `external_reference`，不能标为本实验的 observation。

## 推荐的族内结构

族目录先按目标 PTX opcode 或不可拆的 opcode 子族建立子目录。类型、位宽、限定符、
scope 和其他合法语义形态属于该指令目录内的 `SF`，不继续拆成目录。每个指令目录
至少包含范围说明，因此不创建无说明的空目录：

```text
<family>/
├── README.md
└── <ptx-opcode>/
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
2. `allocation`：规范化寄存器编号，但保留寄存器类别、寄存器对、predicate polarity 和 operand slot。
3. `semantic`：按目标 effect slice 的 def-use/CFG 结构规范化。

删除、融合、展开、复制和无法归属不是普通 opcode 序列，而是独立 lowering 类别。

## 组合覆盖

- 单因素差分用于解释主效应，不用于筛掉后续组合因素。
- 所有因素都应进入受约束的组合覆盖。
- 对高风险因素簇做局部全因子或更高阶覆盖。
- 只完成 t-wise 覆盖时，结论只能写为 “t-wise 覆盖完成”。
- 只有穷举冻结后的有限输入空间，才能写为“相对于该输入空间完整”。

族目录可从 [族实验模板.md](族实验模板.md) 复制计划结构。

## 可复用基础设施

| 入口 | 用途 |
|---|---|
| [`schemas/factors.schema.json`](schemas/factors.schema.json) | 校验指令因子、水平、约束和覆盖目标 |
| [`schemas/manifest.schema.json`](schemas/manifest.schema.json) | 校验 testcase manifest 的共同身份、语义形态和上下文字段 |
| [`schemas/attribution.schema.json`](schemas/attribution.schema.json) | 校验 PTX occurrence 到 SASS effect slice 的归属记录 |
| [`schemas/mapping_rules.schema.json`](schemas/mapping_rules.schema.json) | 校验带证据等级、适用条件和反例计数的映射规则 |
| [`templates/family_README.md`](templates/family_README.md) | 新指令族索引模板 |
| [`templates/opcode_README.md`](templates/opcode_README.md) | 新 opcode 研究目录模板 |
| [`templates/factors.yaml`](templates/factors.yaml) | 因子模型模板 |
| [`templates/suite_runtime.py`](templates/suite_runtime.py) | 自包含 opcode 套件 runtime 模板（按 `Spec.family` 参数化，复制后不改动） |
| [`templates/建族套件指南.md`](templates/建族套件指南.md) | 族实验设计 + 套件建设流程与对抗式审查检查单 |
| [`tools/validate_manifest.py`](tools/validate_manifest.py) | 使用 Python 标准库检查 JSONL、必需字段和 ID 唯一性 |
| [`tools/normalize_sass.py`](tools/normalize_sass.py) | 生成保留寄存器类别和别名关系的 allocation 表示 |
| [`tools/check_coverage.py`](tools/check_coverage.py) | 统计指定因子的一阶水平与二阶组合覆盖 |
| [`tools/audit_families.py`](tools/audit_families.py) | 审计族目录交付物与对抗式审查检查单落实情况 |

共同术语分别见 [`terminology/observation_levels.md`](terminology/observation_levels.md)、[`terminology/status_model.md`](terminology/status_model.md)和[`terminology/evidence_levels.md`](terminology/evidence_levels.md)。JSON Schema 用于稳定跨指令族的共同外壳，不限制各族在 `semantic_form`、`context`、`observation` 和 `evidence` 中增加指令专属字段。

`attribution.schema.json` 描述的是规范化后的 occurrence 级交换记录，不直接等同于各实验目录保存的原始 attribution JSONL。以 Thor `tcgen05.mma` 为例，原始文件按 case 组织并在 `occurrences[]` 中嵌套目标；接入共同 schema 时应先展开 occurrence，并显式选择 `exact`、`allocation` 或 `semantic` 观察层，不能把原始文件未经转换直接宣称为 schema-valid。

# 05 · CUDA Core 整数指令

状态：`IN_PROGRESS`（[实验设计.md](实验设计.md) 已完成全族 26 opcode 的实测校准与结构分类；`mad` 套件已建成并通过首轮自检：35 syntax + 43 expanded case × O0–O3 共 312 次编译/归属 PASS，9 个带诊断锚定的负向探针全部按预期拒绝。旗舰发现：非 sat 的 `mad.hi.{s32,u32}` 其 c 操作数被物化零替换而不参与累加，见设计文档）

## 范围

覆盖 add/sub、mul/mad、div/rem、shift、logic、compare、select 和 move，
包括 32/64-bit、signed/unsigned/bit 形态。

## 具体指令目录

- 基本算术：[`add`](add/)、[`sub`](sub/)、[`mul`](mul/)、[`mad`](mad/)、
  [`div`](div/)、[`rem`](rem/)、[`abs`](abs/)、[`neg`](neg/)、
  [`min`](min/)、[`max`](max/)；
- 扩展精度：[`addc`](addc/)、[`subc`](subc/)、[`madc`](madc/)；
- 移位与逻辑：[`shl`](shl/)、[`shr`](shr/)、[`shf`](shf/)、
  [`and`](and/)、[`or`](or/)、[`xor`](xor/)、[`not`](not/)、[`cnot`](cnot/)；
- 比较与选择：[`set`](set/)、[`setp`](setp/)、[`selp`](selp/)、
  [`slct`](slct/)；
- 数据移动：[`mov`](mov/)。

## 优先上下文

- 每个源槽的寄存器、RZ、立即数和 modifier；
- destination/source overlap、重复源、交换律和常量等价类；
- mul-add、add-add、shift-logic、compare-branch 等融合；
- single/multi-use、consumer 类型、guard 兼容和跨块 def-use；
- wide result、寄存器对、carry、sat、spill 和重计算。

## 高风险簇

`producer × consumer × use-count × guard × modifier` 以及
`source-slot × operand-kind × value-class` 不得先按主效应筛选。

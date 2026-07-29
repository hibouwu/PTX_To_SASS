# 05 · CUDA Core 整数指令

状态：`NOT_STARTED`

## 范围

覆盖 add/sub、mul/mad、div/rem、shift、logic、compare、select 和 move，
包括 32/64-bit、signed/unsigned/bit 形态。

## 优先上下文

- 每个源槽的寄存器、RZ、立即数和 modifier；
- destination/source overlap、重复源、交换律和常量等价类；
- mul-add、add-add、shift-logic、compare-branch 等融合；
- single/multi-use、consumer 类型、guard 兼容和跨块 def-use；
- wide result、寄存器对、carry、sat、spill 和重计算。

## 高风险簇

`producer × consumer × use-count × guard × modifier` 以及
`source-slot × operand-kind × value-class` 不得先按主效应筛选。


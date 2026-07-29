# 14 · Bit operations

状态：`NOT_STARTED`

## 范围

覆盖 lop3、prmt、bfe/bfi、popc、clz、brev、fns 和 bmsk。

## 优先上下文

- 位掩码、power-of-two、全零/全一、符号位和立即数编码类；
- 每个源槽、重复源、RZ、not/neg modifier；
- extract/insert + logic、shift + logic、descriptor encode/decode pattern；
- single/multi-use、predicate/branch consumer 和 CSE；
- 32/64-bit 扩展、截断和 pack/unpack。

## 高风险簇

立即数类别不能只取单个代表值；需要规则驱动边界变异与独立 bit-pattern corpus。


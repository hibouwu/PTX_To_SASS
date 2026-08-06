# 14 · Bit operations

状态：`IN_PROGRESS`（[实验设计.md](实验设计.md) 已完成全 10 opcode 的实测校准；`lop3` 套件已建成并通过首轮自检：37 syntax + 61 expanded case × O0–O3 共 392 次编译/归属 PASS，15 个带诊断锚定的负向探针全部按预期拒绝。关键发现：immLut 只在 b 槽原样透传、a/c 槽立即数触发 immLut 代数置换；immLut 越界不报错而静默截断/回绕；`lop3.BoolOp` 双目的消费时一对二 lowering；本目标无独立 BFE/BFI 指令）

## 范围

覆盖 lop3、prmt、bfe/bfi、popc、clz、brev、fns 和 bmsk。

## 具体指令目录

- [`lop3`](lop3/)
- [`prmt`](prmt/)
- [`bfe`](bfe/)
- [`bfi`](bfi/)
- [`popc`](popc/)
- [`clz`](clz/)
- [`bfind`](bfind/)
- [`brev`](brev/)
- [`fns`](fns/)
- [`bmsk`](bmsk/)

普通 `and/or/xor/not` 与移位由 `05_cuda_core_int` 持有。

## 优先上下文

- 位掩码、power-of-two、全零/全一、符号位和立即数编码类；
- 每个源槽、重复源、RZ、not/neg modifier；
- extract/insert + logic、shift + logic、descriptor encode/decode pattern；
- single/multi-use、predicate/branch consumer 和 CSE；
- 32/64-bit 扩展、截断和 pack/unpack。

## 高风险簇

立即数类别不能只取单个代表值；需要规则驱动边界变异与独立 bit-pattern corpus。

# 17 · Quantization

状态：`FRAMEWORK_VALIDATED`（首轮：`dp4a` 旗舰套件 14 syntax + 26 expanded case，O0–O3 共 160 次编译/归属 PASS，10 负向探针全绿；其余 4 个 opcode 完成校准，`DESIGNED`）

详见 [`实验设计.md`](实验设计.md)：5 个 opcode 的实测助记符表、satfinite/rounding 合法面、对抗式审查缺口落实、STATIC_ONLY 边界（逐 lane oracle 归运行时）。

## 范围

覆盖 dp4a/dp2a、整数 pack、FP8 conversion 和量化相关 mixed-precision pattern。

## 具体指令目录

- [`dp4a`](dp4a/) — `FRAMEWORK_VALIDATED`，套件见 [`dp4a/thor_ptx90/`](dp4a/thor_ptx90/)
- [`dp2a`](dp2a/) — `DESIGNED`
- [`cvt.pack`](cvt.pack/) — `DESIGNED`
- [`cvt.e4m3x2`](cvt.e4m3x2/) — `DESIGNED`
- [`cvt.e5m2x2`](cvt.e5m2x2/) — `DESIGNED`

## 优先上下文

- signed/unsigned 输入、accumulator 类型和 destination overlap；
- pack lane 顺序、sat、rounding、finite-only 和特殊 bit pattern；
- scalar load + pack、packed load、convert + arithmetic；
- zero point、scale-like producer、single/multi-use 和融合；
- 立即数、GPR/UR 路由和 predicate。

## 本族完成门槛

每个 packed/quantized 候选必须有逐 lane oracle，并覆盖 saturation 两侧和 rounding tie。

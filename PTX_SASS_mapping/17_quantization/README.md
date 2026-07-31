# 17 · Quantization

状态：`NOT_STARTED`

## 范围

覆盖 dp4a/dp2a、整数 pack、FP8 conversion 和量化相关 mixed-precision pattern。

## 具体指令目录

- [`dp4a`](dp4a/)
- [`dp2a`](dp2a/)
- [`cvt.pack`](cvt.pack/)
- [`cvt.e4m3x2`](cvt.e4m3x2/)
- [`cvt.e5m2x2`](cvt.e5m2x2/)

## 优先上下文

- signed/unsigned 输入、accumulator 类型和 destination overlap；
- pack lane 顺序、sat、rounding、finite-only 和特殊 bit pattern；
- scalar load + pack、packed load、convert + arithmetic；
- zero point、scale-like producer、single/multi-use 和融合；
- 立即数、GPR/UR 路由和 predicate。

## 本族完成门槛

每个 packed/quantized 候选必须有逐 lane oracle，并覆盖 saturation 两侧和 rounding tie。

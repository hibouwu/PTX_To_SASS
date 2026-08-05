# `cvt`（E5M2x2）

状态：`DESIGNED`（轴与合法面已校准，见 [`../实验设计.md`](../实验设计.md)；待写 `thor_ptx90/suite_spec.py`）

负责 F32 与 E5M2x2 间转换、rounding、satfinite、特殊值和逐 lane oracle。实测：`cvt.rn.satfinite[.relu].e5m2x2.{f32,f16x2} d,a[,b]` → `F2FP.SATFINITE[.RELU].E5M2.{F32.PACK_AB,F16.UNPACK_B}_MERGE_C d,...,RZ`；反向 `cvt.rn.f16x2.e5m2x2 d,a` → `F2FP.F16.E5M2.UNPACK_B d,a`，**不接受** `.satfinite`。修饰符合法面（`.satfinite` 强制、`.rn`-only、`.relu` 合法）与 `e4m3x2` 逐条分别实测一致，非外推。逐 lane 数值 oracle、rounding tie 留待运行时验证（`STATIC_ONLY`）。

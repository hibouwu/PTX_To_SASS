# `cvt`（E4M3x2）

状态：`DESIGNED`（轴与合法面已校准，见 [`../实验设计.md`](../实验设计.md)；待写 `thor_ptx90/suite_spec.py`）

负责 F32 与 E4M3x2 间转换、rounding、satfinite、特殊值和逐 lane oracle。实测：`cvt.rn.satfinite[.relu].e4m3x2.{f32,f16x2} d,a[,b]` → `F2FP.SATFINITE[.RELU].E4M3.{F32.PACK_AB,F16.UNPACK_B}_MERGE_C d,...,RZ`（SASS 恒带 PTX 未暴露的第三源槽，自动填 `RZ`）；反向 `cvt.rn.f16x2.e4m3x2 d,a` → `F2FP.F16.E4M3.UNPACK_B d,a`，**不接受** `.satfinite`（与打包方向的"强制"互斥）。`.satfinite` 在打包方向强制，`.rn` 是唯一合法舍入档位（`.rz`/`.rp`/`.rm` 均非法）。逐 lane 数值 oracle、rounding tie 留待运行时验证（`STATIC_ONLY`）。

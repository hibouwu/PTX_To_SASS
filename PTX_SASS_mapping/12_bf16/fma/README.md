# `fma`（BF16/BF16x2）

状态：`FRAMEWORK_VALIDATED`（本机 CUDA 13.0：8 个 syntax + 25 个 expanded case 于 O0–O3 共 132 次编译、反汇编与 `HFMA2.BF16_V2`/`FFMA.RZ`/`FFMA.RM`/`FFMA.RP` 归属全部通过；11 个负向探针含 2 条 P0-2 补集抽样，全部按预期拒绝且诊断子串匹配）

负责 BF16/BF16x2 fused multiply-add、accumulator 和 packed lane。

## 一句话实测映射摘要

`fma` 是本族唯一强制显式舍入 token、且唯一接受 `.rz`/`.rm`/`.rp` 的 opcode：`fma.rn.bf16`/`fma.{rn,rz,rm,rp}.bf16x2` 全部直译为原生 `HFMA2.BF16_V2`（packed 路径对舍入 token 逐位无感，`.rn`/`.rz`/`.rm`/`.rp` 编码完全相同）；只有 `fma.{rz,rm,rp}.bf16`（标量）会降级为 F32 模拟序列：`HADD2.F32` 展宽三个操作数 → `FFMA.RZ`/`RM`/`RP` → `F2F.F16.F32` 收窄。`.ftz`/`.sat` 在两条路径上一律非法。详见族级 [实验设计.md](../实验设计.md)。

## 一键运行

```bash
cd PTX_SASS_mapping/12_bf16/fma/thor_ptx90
./check_all.sh 8
```

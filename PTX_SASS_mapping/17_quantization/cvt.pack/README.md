# `cvt.pack`

状态：`DESIGNED`（轴与合法面已校准，见 [`../实验设计.md`](../实验设计.md)；待写 `thor_ptx90/suite_spec.py`）

负责整数 pack、lane 顺序、sat、rounding 和 pack consumer。实测：`cvt.pack.sat.{s8,u8}.s32.b32 d,a,b,c`（4 操作数链式语法，`c` 是待合并的高两字节来源）→ `I2IP.{S8,U8}.S32.SAT d,a,b,c`；`.sat` 强制，无舍入修饰符。**证伪记录**：规范阅读预期存在的 `.s16`/`.u16` 目的类型 2 操作数形态在本工具链版本上**全部被拒**（`Unexpected instruction types specified for 'cvt.pack'`），本族目的类型合法面目前只有 `{s8, u8}`。

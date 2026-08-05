# `dp2a`

状态：`DESIGNED`（轴与合法面已校准，见 [`../实验设计.md`](../实验设计.md)；待写 `thor_ptx90/suite_spec.py`）

负责两路混合宽度整数点积累加、lo/hi、signedness 和 accumulator。实测：`dp2a.mode.atype.btype d,a,b,c`（`mode` ∈ `{lo,hi}` 强制，`atype`/`btype` ∈ `{u32,s32}`）→ `IDP.2A.{LO,HI}.{U16,S16}.{U8,S8} d,a,b,c`；`atype` 描述 16 位操作数 `a` 的符号（进 `U16`/`S16`），`btype` 描述 8 位操作数 `b` 的符号（进 `U8`/`S8`）——两个类型后缀描述不同宽度的操作数，与 `dp4a` 不同；`b` 接受立即数。

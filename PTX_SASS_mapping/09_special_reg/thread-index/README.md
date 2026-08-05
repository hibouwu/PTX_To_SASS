# Thread index special registers

状态：`FRAMEWORK_VALIDATED`（Thor/PTX 9.0 静态套件见 [thor_ptx90/](thor_ptx90/)：24 syntax + 46 expanded case × O0–O3 共 280 次编译/归属 PASS，9 个带诊断锚定的负向探针全部按预期拒绝；forward rule 184、inverse signature 36）

负责 `%tid.{x,y,z}` 与 `%ntid.{x,y,z}` 的读取、位宽和 consumer pattern。

核心实测结论（详见 [../实验设计.md](../实验设计.md)）：`%tid.*` 恒为 `S2R SR_TID.*`（永不 S2UR，逐 lane 非 uniform）；`%ntid.*` 恒为常量 bank `LDC c[0x0][0x360/0x364/0x368]`，`.reqntid` 不把它折成立即数；`%tid.w` 合法且折叠为 `MOV RZ`；`.r/.g/.b/.a` 是合法 RGBA 别名；`shfl.sync.idx` 广播对 `%ntid`（可证明 uniform）被消除、对 `%tid` 保留。

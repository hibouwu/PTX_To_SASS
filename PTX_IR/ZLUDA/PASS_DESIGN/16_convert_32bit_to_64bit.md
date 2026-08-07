# Pass 16：`convert_32bit_to_64bit`

源码：[`../ptx/src/pass/convert_32bit_to_64bit.rs`](../ptx/src/pass/convert_32bit_to_64bit.rs)

## 契约与变换

仅 `.address_size 32` 执行。Pass 收集受支持的 `.global/.const` 单维 b8/u8 初始化数组，删除原对象，为每个有 body 的 kernel 追加一个 64 位隐式内存指针及每个 global 的 32 位伪指针参数，改写引用，并产生 `ModuleMetadata32Bit`。`.shared` 和 texref 透传。

输出不变量：受支持的 32 位全局对象由 metadata 与 hidden arguments 承载；64 位 module 完全跳过本 Pass。

## 顺序依赖

需要 Pass 15 已暴露变量访问；必须在 Pass 17 按 `is_32bit` 选择 BitToPtr 规则前运行。

## 现代指令接入

第一阶段现代指令建议只接受 `.address_size 64`。若必须支持 32 位，所有 descriptor、TMEM/shared/cluster 地址和 hidden ABI 都要纳入本 Pass 的明确模型，不能把 32 位 TMEM address 与 module 32 位指针模型混淆。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| 有 body 的普通 `.func` | `!is_kernel` 直接 `error_todo()` | 32 位函数调用不支持 |
| 非单维 b8/u8 global 或复杂 initializer | `collect_globals` 返回 TODO | 支持范围很窄 |
| 新现代地址空间 | 只为现有 global/shared/texref 分类 | 没有自动支持 |

## 测试要求

当前无专属 fixture。补 metadata、hidden argument 顺序/布局、多 global、shared/texref 透传、普通函数负例、复杂 initializer 负例，以及现代指令明确拒绝 32 位 module 的测试。

# Pass 04：`optimize_function_arguments`

源码：[`../ptx/src/pass/optimize_function_arguments.rs`](../ptx/src/pass/optimize_function_arguments.rs)

## 契约与变换

本 Pass 把一维、unsized 的 `.param b8[]` 改成 `.param b32[ceil(n/4)]`，并同步 resolver、非 kernel 函数签名、函数体变量以及 call details。多维数组和其他类型不变。

输出不变量仅针对该窄形态；它不是通用 ABI 优化。源码注释明确说明该规则源于 AMDGPU 效率动机。

## 顺序依赖

需在函数 ABI 被 `deparamize_functions` 展开之前运行，否则参数槽、call 签名和临时值会产生多处重写点。

## 现代指令接入

现代指令 descriptor 或 opaque parameter 不应自动套用此重排。若其字节数组具有 ABI 固定布局，应排除本 Pass 或先证明四字节重组保持对齐、大小和读取语义。

不建议为现代 opcode新增 Pass；更应评估当前 Pass 是否应限制在 AMDGPU 路径。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| kernel signature 的 `b8[]` | method signature 只在 `!is_kernel()` 时修改 | kernel 参数不改，符合当前实现 |
| kernel body 内局部 `.param b8[]` | body statement 对所有 method 遍历 | 仍会改写，不能概括为“kernel 完全跳过” |
| descriptor 要求逐字节布局 | 无语义类型或排除名单 | 存在 ABI 破坏风险 |

## 测试要求

当前无专属 fixture。补齐非 kernel 签名、kernel 签名不变、kernel body 局部 param、call details、多维数组和 descriptor 排除测试。

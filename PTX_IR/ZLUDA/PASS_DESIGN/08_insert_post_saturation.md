# Pass 08：`insert_post_saturation`

源码：[`../ptx/src/pass/insert_post_saturation.rs`](../ptx/src/pass/insert_post_saturation.rs)

## 契约与变换

本 Pass 对浮点 `add/fma/mad/mul/sub` 及部分浮点 `cvt` 的 `saturate: true` 形式：把原 destination 替换为临时寄存器，再追加 `Statement::FpSaturate { dst, src, type_ }`。其他 variant 原样保留。

输出不变量：被覆盖的 `.sat` 语义已从 opcode modifier 变为显式后处理；整数 saturation 和未列入模式不由本 Pass处理。

## 顺序依赖

应在 helper lowering 和 LLVM emit 前保留原 opcode 的 saturation 信息；在 Pass 7 后可直接操作 ID destination。

## 现代指令接入

新增 enum variant 会迫使当前穷尽 `match` 重新分类。新 `.sat/.relu/satfinite` 语义不能一律映射到 `FpSaturate`：先确认范围、NaN、无穷和舍入规则相同。通常扩展本 Pass，不需要新 Pass。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| 新 instruction variant | `run_instruction` 是穷尽 match | 编译会提示分类缺失，这是正向防线 |
| `.relu` 或 `satfinite` | 仅匹配 `saturate: true` 的既有字段 | 不能声称自动支持 |
| destination 是 async pending tuple | Pass 7 已先决定 tuple 写回形态 | 必须先通过专用 marker 隔离，不能在此补救 |

## 测试要求

当前无专属 fixture。为每个匹配 opcode 加“modifier 清除/临时 destination/后处理顺序”测试，并增加 NaN、±Inf、负零及未匹配现代 modifier 负例。

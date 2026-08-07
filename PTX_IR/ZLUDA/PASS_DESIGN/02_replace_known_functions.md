# Pass 02：`replace_known_functions`

源码：[`../ptx/src/pass/replace_known_functions.rs`](../ptx/src/pass/replace_known_functions.rs)

## 契约与变换

输入名称已解析为 ID。本 Pass 仅检查 method 名称；若精确等于 `__assertfail` 或 `vprintf`，就在 resolver 中改名为 `__zluda_ptx_impl_*`。函数签名、call statement 和 linkage 不变，call 通过同一 ID 自动观察到新名称。

输出不变量：这两个保留名称指向 ZLUDA helper 命名空间。它不是通用 runtime ABI 表，也不验证 helper 定义是否存在。

## 顺序依赖

必须在 ID 建立后运行。宜早于 helper 声明收集和 LLVM emit，避免同一函数出现两个最终符号。

## 现代指令接入

现代 opcode 不应在此处理。只有新增外部 PTX runtime ABI 符号时才扩展名单；NVVM intrinsic 应由 Pass 18 或 emitter 注册。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| 用户自己定义名为 `vprintf` 的函数 | 所有 `Method` 都按名称改写，不区分 declaration/definition | 可能误改用户定义；需 ABI/linkage 测试 |
| helper 名称冲突 | 直接覆盖 resolver 中的文本名 | 没有冲突检测 |
| 新 runtime 符号 | 固定数组仅两个名称 | 会静默不处理，必须显式登记 |

## 测试要求

当前无专属 fixture。补充 declaration、definition、同名冲突、call 名称传播和非目标名称不变测试。

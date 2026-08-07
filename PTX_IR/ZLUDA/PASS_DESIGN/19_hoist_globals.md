# Pass 19：`hoist_globals`

源码：[`../ptx/src/pass/hoist_globals.rs`](../ptx/src/pass/hoist_globals.rs)

## 契约与变换

本 Pass 从函数体提取 `StateSpace::Global/Const/Shared` 的 `Variable` statement，作为 `LinkingDirective::NONE` 的 module directive 插到所属 method 前；ID、resolver type/space 和 use 不变。其他 statement 原样保留。

输出不变量：上述三种可发射对象不再嵌在函数体。它不做地址空间合法性、去重、初始化或 linkage 推导。

## 顺序依赖

位于最终 emit 前，确保 LLVM global 先于函数体使用被统一创建。应晚于可能在函数体中新增变量的所有 Pass。

## 现代指令接入

若 cluster/CTA shared descriptor 引入函数体变量，需要决定它们是 LLVM module object、kernel-scoped resource还是纯 handle；不能盲目把 `SharedCta/SharedCluster` 加入现有三类。确定为 module object 后再扩展本 Pass和 emitter。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| `SharedCta/SharedCluster` body variable | match 只包含 Global/Const/Shared | 会留在 body，当前 emitter/space mapping 可能失败 |
| 两个函数内同名/同 ID global | Pass 不去重，只按出现顺序提升 | 依赖前置 resolver 保证身份；需 module 验证 |
| 新 Pass 在其后创建 global | 当前它是最后一个变换 Pass | 未来插入顺序必须保持 hoist 最后或再次 hoist |

## 测试要求

当前无专属 fixture。补三种空间、多个函数、初始化、重复/冲突、保留 use ID、cluster/CTA 明确拒绝或支持，以及 emit 后 module verifier 测试。

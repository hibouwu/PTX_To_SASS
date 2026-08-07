# Pass 15：`insert_explicit_load_store`

源码：[`../ptx/src/pass/insert_explicit_load_store.rs`](../ptx/src/pass/insert_explicit_load_store.rs)

## 契约与变换

本 Pass 将函数体中的 `.reg` 变量声明改为 `.local` slot，并在每次 source use 前插 `ld.local`、每次 destination def 后插 `st.local`；局部 `.param` 变量改为 `.local` 并修正已有 ld/st 空间。kernel 输入参数改为内部 `ParamEntry`，普通函数返回值在 `ret` 处形成 `RetValue`。

输出不变量：变量存储与 value use/def 已显式分离，后续 LLVM 可用 mem2reg 恢复 SSA。原本就是 `.local` 的变量保持不变。

## 顺序依赖

必须晚于函数 ABI 和最终 CFG，早于地址宽度/隐式转换。任何 pending result 都必须在进入本 Pass 前物化成 ready 的普通 IR。

## 现代指令接入

同步且结果立即可用的 opcode 可复用 visitor。tcgen05.ld 等异步 destination 不能在本 Pass 内临时延迟：Pass 7 已可能提前生成消费。正确边界是前置协议 Pass 在 wait 后生成普通 `RepackVector`，本 Pass 保持通用并拒绝残留 marker。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| async tuple destination | visitor 对所有 destination 立即排入 post store | 若无前置 marker/materializer 会错误消费 |
| 新 statement variant 的 def/use 元数据错误 | 通用 `visit_map` 决定 pre/post | 可能静默插错位置，必须定向测试 |
| cluster/shared variable | declaration 本身透传，不转 local | 并不等于后续 emitter 已支持该空间 |

## 测试要求

当前无专属 fixture。补 source/destination、多目标、向量 repack、kernel ParamEntry、函数 return、地址对象和“wait 后才出现 extract/store”的 async 测试；增加残留 pending marker 的内部错误断言。

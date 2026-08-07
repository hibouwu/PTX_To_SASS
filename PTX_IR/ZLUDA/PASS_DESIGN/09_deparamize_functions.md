# Pass 09：`deparamize_functions`

源码：[`../ptx/src/pass/deparamize_functions.rs`](../ptx/src/pass/deparamize_functions.rs)

## 契约与变换

普通 `.func` 的 `.param` 输入/返回参数改为 `.reg` ABI：定义入口以局部 param slot 和 `st.param` 恢复原函数体视图；`ret` 前从返回 slot `ld.param`；call site 在调用前后插入相反方向的 load/store。kernel 不做同样的签名转换。声明没有 body，因此只改签名，不插桥接 statement。

输出不变量：普通函数跨 LLVM 函数边界的值位于 `.reg`；PTX 参数槽只作为函数体/call 周围的显式桥接。

## 顺序依赖

必须在参数数组规范化后、Pass 15 把变量转为 local 表示前运行。

## 现代指令接入

若 descriptor、mbarrier handle 或 TMEM 地址跨函数边界，必须保留其值语义和地址空间；不能只因底层位宽相同就按普通 integer `.reg` 传递。通常扩展参数类型模型，不新增 Pass。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| 非 kernel 参数空间不是 Param/Reg | 明确返回 `error_unreachable` | 复杂 `ParamFunc` 等尚不支持 |
| 一个函数多个 ret | 每个 ret 都插返回 load；后续 Pass 12 再合并出口 | 顺序设计一致 |
| declaration 与 definition ABI | declaration 只改签名，definition加桥接 | 需链接签名一致性测试 |

## 测试要求

当前无专属 fixture。补输入、返回、多返回、extern declaration、call round-trip、kernel 不变和语义化地址/descriptor 参数测试。

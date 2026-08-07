# Pass 07：`expand_operands`

源码：[`../ptx/src/pass/expand_operands.rs`](../ptx/src/pass/expand_operands.rs)

## 契约与变换

输入 operand 仍可能是 register、immediate、register+offset、vector member 或 tuple。Pass 将 instruction operand 统一成 `SpirvWord`：

- immediate → `Constant`；
- `.reg + offset` → constant + integer `Add`；
- 可寻址对象 + offset → `PtrAccess`；
- vector member → `VectorRead/VectorWrite`；
- tuple → packed temporary + `RepackVector`。

源操作数辅助 statement 位于主指令前，destination 写回位于主指令后。输出不变量：instruction visitor 不再解析复合 operand 语法。

## 顺序依赖

必须在特殊寄存器和函数地址识别之后；其生成的显式 statement 是饱和、ABI、CFG、load/store 和转换 Pass 的共同输入。

## 现代指令接入

新指令只要参数 visitor 元数据正确，普通 immediate/offset 可复用本 Pass。大 tuple、descriptor 和特殊地址值必须验证预期 type/space。异步 destination 不能复用普通 post `RepackVector`：tcgen05.ld 应生成 non-emitting pending-unpack marker，交给 wait 后的协议 Pass 物化。

## 对抗式审查

| 反例 | 源码证据 | 结论 |
| --- | --- | --- |
| tcgen05.ld tuple | `vec_pack(is_dst)` 通过 `Drop` 紧随主指令追加 `RepackVector` | 会在 wait 前消费 pending result；必须修改 |
| 非 `.reg` offset | 统一生成 S64 offset 的 `PtrAccess` | 地址宽度/空间需由后续 Pass 证明 |
| bit scalar 打包且元素数不整除 | 使用 `size_of()/len` 后查 `ScalarType::from_size` | 会类型错误，但需边界测试 |

## 测试要求

现有 fixture 覆盖 immediate、vector operand、vector extract 和部分转换。仍需补 offset 正负值、非法 tuple 宽度、大于 v4 tuple、descriptor，以及 async marker 不提前 `RepackVector` 的顺序测试。

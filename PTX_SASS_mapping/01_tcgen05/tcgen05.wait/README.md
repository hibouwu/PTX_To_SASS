# `tcgen05.wait`

状态：`NOT_STARTED`

## 研究边界

研究 `tcgen05.wait::ld.sync.aligned` 与 `tcgen05.wait::st.sync.aligned` 的 PTX→SASS 映射。两者等待当前线程此前发出的 TMEM load 或 store 完成，不是 CTA/cluster barrier，也不自动发布普通内存访问。

## 主要因素

| 因素 | 计划水平 | 重点问题 |
|---|---|---|
| wait 类别 | `ld`、`st` | 是否选择独立 opcode、modifier 或统一异步 view fence |
| 前序队列 | 空、单操作、多操作、交错 ld/st | wait 覆盖范围和是否合并 |
| 后续 consumer | 寄存器使用、TMEM 重写、dealloc | completion 与 anti-dependency 的真实边界 |
| 控制流 | 直线、uniform branch、divergent 阴性探针 | `.sync.aligned` 的 warp 参与要求 |
| 优化级 | O0–O3 | wait 是否因可证明无依赖而移动或保留 |

## 完成门槛

需要把核心 wait/fence SASS 与调度 NOP 分开归属，并用有/无 wait 的实机对照验证完成语义；不能从反汇编中出现 `FENCE.VIEW.ASYNC.T` 单独推出跨线程可见性。

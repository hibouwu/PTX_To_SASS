# `tcgen05` 内存一致性与完成协议

> 适用范围：PTX ISA 9.0、NVIDIA Thor 架构、编译目标 `sm_110a`
>
> 本文同时使用两类证据：NVIDIA PTX ISA 规定原语的抽象语义；本目录的协议层 PTX、`ptxas` 和 `nvdisasm` 结果证明这些原语在当前目标上的静态编译降级。
>
> 结论边界：本文可以证明"源码可汇编、SASS 形态和静态协议结构"，不能代替双线程/双 CTA 实机 litmus test 来证明运行时可见值和 happens-before 关系。

## 先说结论

`tcgen05` 的内存一致性不能只看一条 fence，而要把四类机制分开：

| 机制 | 回答的问题 | 主要 PTX 原语 | 当前 SASS 见证 |
|---|---|---|---|
| 异步完成 | 先前的异步操作是否已经完成？ | `tcgen05.commit`、`mbarrier.try_wait`、`tcgen05.wait::ld/st` | `UTCBAR*`、`SYNCS.PHASECHK*`、`LDTM/STTM`、`FENCE.VIEW.ASYNC.T` |
| 跨线程排序 | 一个线程的 tcgen05 操作如何排在同步点前后？ | `tcgen05.fence::before_thread_sync`/`after_thread_sync` | 上下文相关；可以不产生同名独立指令，也可以改变 `BAR.SYNC`、`NOP` 和调度布局 |
| 普通内存可见性 | 同步对象之前的普通内存访问何时对其他线程可见？ | `mbarrier.arrive.release` + 成功的 `mbarrier.try_wait.acquire` | 集群（cluster）release/acquire 见到 `MEMBAR.ALL.CTA/GPU`、`ERRBAR`、`CGAERRBAR`；具体序列受上下文优化影响 |
| 参与范围与资源生命周期 | 哪些 CTA 参与，TMEM/mbarrier 何时可复用？ | `.cta/.cluster`、`.cta_group::1/2`、alloc/dealloc/relinquish、mbarrier init/inval | `.2CTA`、`SYNCS.EXCH/CCTL`、`UVIRTCOUNT.DEALLOC.SMPOOL` 等；生命周期管理本身不等于内存排序 |

最容易混淆的三点：

- `tcgen05.commit` 跟踪先前 `tcgen05.mma`/`cp`/`shift` 的完成，并在完成后触发 mbarrier arrive。它不是面向所有普通内存访问的通用 fence。
- `mbarrier` 的"phase 已完成"和普通内存的 release/acquire 可见性是相关但不同的属性。`.relaxed` 只检查 phase，不提供普通内存排序与可见性保证。
- `tcgen05.wait::ld/st` 等待当前线程先前的 TMEM load/store 完成，并要求 warp 对齐执行。它不是 CTA/集群线程同步，也不能单独把数据发布给另一个线程。

## 一条完整 happens-before 链需要什么

跨线程传递 tcgen05 工作时，可以把协议理解为三段：

```text
生产者 tcgen05 操作
    → 完成或流水线排序：commit / wait / tcgen05.fence::before_thread_sync
    → 跨线程同步：mbarrier arrive + 成功 wait，或其他执行排序原语
    → 消费者 tcgen05 操作：tcgen05.fence::after_thread_sync 后再发射
```

如果还要让普通全局/共享内存访问跨线程可见，则同步段必须具有匹配的 release/acquire 语义和足够大的范围（scope）：

```text
生产者普通内存访问
    → mbarrier.arrive.release.<scope>
    → 同一 phase 完成
    → mbarrier.try_wait.acquire.<scope> 返回 true
    → 消费者后续普通内存访问
```

NVIDIA PTX ISA 将 release pattern 定义为让本线程在它之前的操作参与同步，将 acquire pattern 限定到它之后的操作。成功返回的 acquire `mbarrier.try_wait`/`test_wait` 才形成 acquire pattern。`.relaxed` 明确不提供内存排序或可见性保证。双方必须处于能相互同步的 scope 内。参见 [NVIDIA PTX ISA：Memory Consistency Model 与 mbarrier](https://docs.nvidia.com/cuda/parallel-thread-execution/)。

## `tcgen05.commit`：MMA 完成通知，不是普通内存 fence

规范上，`tcgen05.commit.cta_group::N.mbarrier::arrive::one` 使 mbarrier 跟踪当前线程此前发出的、同一 CTA group 的异步 `tcgen05.mma`/`cp`/`shift`。这些操作完成后，系统以 count 1 对 mbarrier 执行 cluster-scope arrive。它还隐含先前 tcgen05 操作到该同步点的 `before_thread_sync` 排序，因此紧跟 commit 时通常不需要再写一个显式 `tcgen05.fence::before_thread_sync`。参见 [NVIDIA PTX ISA：tcgen05.commit](https://docs.nvidia.com/cuda/parallel-thread-execution/)。

当前 O3 静态映射完整覆盖 CTA group 1/2、通用（generic）/共享集群（shared::cluster）和组播（multicast）：

| PTX commit 形态 | SASS |
|---|---|
| `cta_group::1 ... [%mbar]` | `UTCBAR [UR4], URZ` |
| `cta_group::1 ... shared::cluster [mbar_obj]` | `UTCBAR [UR4], URZ` |
| `cta_group::1 ... shared::cluster.multicast::cluster [mbar_obj], %cta_mask` | `UTCBAR.MULTICAST [UR4], URZ, UR5` |
| `cta_group::2 ... [%mbar]` | `UTCBAR.2CTA [UR4], URZ` |
| `cta_group::2 ... shared::cluster [mbar_obj]` | `UTCBAR.2CTA [UR4], URZ` |
| `cta_group::2 ... shared::cluster.multicast::cluster [mbar_obj], %cta_mask` | `UTCBAR.2CTA.MULTICAST [UR4], URZ, UR5` |

由此可以确定：CTA group 进入 `.2CTA`；multicast 进入 `.MULTICAST` 并增加 CTA mask 操作数；通用与直接 `shared::cluster` 地址形式在核心 commit 助记符上没有区别。地址准备仍可能不同，所以不能只凭核心助记符反推 PTX 地址空间写法。

## `mbarrier`：完成状态与普通内存同步的连接点

当前协议矩阵对四个组合分别生成了独立用例：CTA/cluster scope × relaxed/release-acquire。共同生命周期是：

```ptx
mbarrier.init.shared::cta.b64 [mbar_obj], 1;
bar.cta.sync 0;
mbarrier.arrive.<sem>.<scope>.shared::cta.b64 _, [mbar_obj];
mbarrier.try_wait.parity.<sem>.<scope>.shared::cta.b64 %complete, [mbar_obj], 0;
bar.cta.sync 0;
mbarrier.inval.shared::cta.b64 [mbar_obj];
```

初始化、phase 检查和失效在四种 case 中都能看到同一骨架：

```sass
SYNCS.EXCH.64 URZ, [UR6], UR4;
BAR.SYNC.DEFER_BLOCKING 0x0;
SYNCS.ARRIVE.TRANS64.A1T0 RZ, [UR6], RZ;
SYNCS.PHASECHK.TRANS64.TRYWAIT PT, [UR6], R0;
BAR.SYNC.DEFER_BLOCKING 0x0;
SYNCS.CCTL.IV [UR6];
```

cluster scope 的 release/acquire case 相对 relaxed case 在 arrive 前增加：

```sass
MEMBAR.ALL.CTA;
MEMBAR.ALL.GPU;
ERRBAR;
CGAERRBAR;
```

这组差分证明 cluster release/acquire 会改变实际编译降级，但不能把四条 SASS 各自机械归因给 release 或 acquire，因为该 case 同时改变 arrive 和 wait 的语义，周围还有 CTA barrier。CTA scope 的 relaxed 与 release/acquire 在当前 O0/O3 case 中得到相同可见 SASS 骨架——编译器可以利用现有 `BAR.SYNC` 和目标语义消除冗余，不表示 PTX 层的 `.release`/`.acquire` 与 `.relaxed` 等价。

### scope 与 state space 不是一回事

在 `mbarrier.arrive.release.cluster.shared::cta` 中：

- `.cluster` 是内存同步范围（memory synchronization scope），决定哪些线程能直接观察同步效果。
- `.shared::cta` 是 mbarrier 对象所在的地址空间。
- 两者可以同时出现，不能把 `.shared::cta` 误读为"只能做 CTA scope 同步"。

## `tcgen05.fence`：跨线程 tcgen05 排序的代码移动边界

`tcgen05.fence::before_thread_sync` 把它之前的异步 tcgen05 操作排在后续 tcgen05 与执行排序操作之前。`tcgen05.fence::after_thread_sync` 把后续异步 tcgen05 操作排在先前 tcgen05 与执行排序操作之后。它们和 mbarrier、barrier、morally strong load/store/atomic 等执行排序原语组合，才能建立跨线程 tcgen05 顺序。参见 [NVIDIA PTX ISA：tcgen05.fence](https://docs.nvidia.com/cuda/parallel-thread-execution/)。

典型生产者/消费者协议是：

```ptx
// producer
tcgen05.cp ...;
tcgen05.fence::before_thread_sync;
mbarrier.arrive.relaxed.cluster ...;

// consumer: wait loop has returned true
tcgen05.fence::after_thread_sync;
tcgen05.mma ...;
```

这里 mbarrier 可以是 relaxed，因为它承担的是线程间执行排序的连接点。如果还需要普通内存的 release/acquire 可见性，就不能用 relaxed 替代相应的 release/acquire 链。

独立 `ctx_fence_before` 和 `ctx_fence_after` 在 O0/O3 都只留下参数装载、`NOP` 与 `EXIT`，没有独立 fence SASS。空 kernel 中没有可供排序的前后操作，约束可以被消除。

在 8 个完整生命周期 case 中，加入三个显式 fence 后，`UTCHMMA`/`UTCBAR`/`SYNCS`/`LDTM`/`STTM` 的核心选择不变，但 `BAR.SYNC.DEFER_BLOCKING` 的位置、寄存器分配和 `NOP` 调度发生变化。`tcgen05.fence` 是上下文相关的排序约束，不能建立"每条 PTX fence 必须对应一个同名 SASS 操作码"的规则。

## `tcgen05.wait::ld/st`：同线程异步 TMEM I/O 完成

规范上，`wait::ld` 阻塞到当前线程此前发出的所有 `tcgen05.ld` 完成，`wait::st` 对此前 `tcgen05.st` 做同样处理。`.sync.aligned` 还要求 warp 中所有线程执行相同 wait 后才继续。这解决完成和 anti-dependency hazard，不是跨线程同步。参见 [NVIDIA PTX ISA：tcgen05.wait](https://docs.nvidia.com/cuda/parallel-thread-execution/)。

`wait::ld` case：

```ptx
tcgen05.ld.sync.aligned.32x32b.x2.b32 {%r0, %r1}, [%taddr];
tcgen05.wait::ld.sync.aligned;
st.global.v2.b32 [%out], {%r0, %r1};
```

```sass
LDTM.x2 R4, tmem[UR4];
STG.E.64 desc[UR4][R2.64], R4;
```

当前 O3 case 没有单独的 wait 助记符，完成约束被吸收到 `LDTM` 与后续使用的调度/依赖中。不能把这一观察推广为所有上下文中 `wait::ld` 都"无指令"。

`wait::st` case：

```ptx
tcgen05.st.sync.aligned.32x32b.x2.b32 [%taddr], {%r0, %r1};
tcgen05.wait::st.sync.aligned;
```

```sass
STTM.x2 tmem[UR4], R2;
FENCE.VIEW.ASYNC.T;
```

这个独立 case 中 `wait::st` 有明确的 `FENCE.VIEW.ASYNC.T` 完成见证。在带 MMA、commit、barrier 和显式 tcgen05 fence 的完整 case 中，相同约束仍可与周围序列合并，因此仍然要按完整上下文解释。

## 完整生命周期实例

覆盖机制最多的 case 是 `effect_cg2_st_wait_explicit_fences`：CTA group 2、TMEM store/load wait、三个 tcgen05 fence、MMA commit、cluster acquire wait、global store、dealloc/relinquish 和 mbarrier inval 都在一个函数中。

O3 的关键机器序列包含：

```sass
STTM.x2 ...;
FENCE.VIEW.ASYNC.T;
UTCHMMA.2CTA ...;
UTCBAR.2CTA ...;
SYNCS.PHASECHK.TRANS64.TRYWAIT ...;
LDTM.x2 ...;
STG.E.64 ...;
BAR.SYNC.DEFER_BLOCKING ...;
UVIRTCOUNT.DEALLOC.SMPOOL ...;
```

这条链可以静态证明完整协议的所有关键构件都成功进入机器码。它不能证明描述符指向有效矩阵、peer CTA 真实参与、MMA 数值正确或跨 CTA 读到了预期值，因为生成 case 使用的是协议骨架而不是实机可观测 litmus test。

## 资源生命周期为什么单独算一层

`tcgen05.alloc`/`dealloc`/`relinquish_alloc_permit` 和 `mbarrier.init`/`inval` 规定资源何时建立、归还和可复用。它们防止"仍有异步使用时就回收 TMEM/mbarrier"这类生命周期错误，但不能替代完成等待和内存排序：

```text
完成确认
    ≠ 跨线程内存可见性
    ≠ CTA 集合到齐
    ≠ 资源已经可以回收
```

安全回收必须同时满足该程序需要的完成条件、参与线程同步和生命周期协议。看到 `UVIRTCOUNT.DEALLOC.SMPOOL` 只能证明 dealloc 编译降级存在，不能单独证明此前所有用户都已完成。

## 当前覆盖范围

协议层生成器共有 42 个 case：34 个独立协议原语 case 和 8 个完整生命周期 case。每个 case 均以 O0/O1/O2/O3 编译，共 168/168 次通过。8 个完整 case 在四个优化级上执行 32 次 SASS 模式检查，32/32 通过，强制检查 `UTCHMMA`、`UTCBAR`、`SYNCS.PHASECHK`、`LDTM`、`UVIRTCOUNT.DEALLOC.SMPOOL`，带 store 的 case 还检查 `STTM`。

按主要变化机制口径，本文覆盖至少 95% 的当前静态内存一致性/完成协议机制：

- CTA group 1/2 的 commit，以及通用、shared::cluster、multicast 三种 mbarrier 目标形式。
- mbarrier 的 CTA/cluster scope 与 relaxed/release-acquire 组合。
- `before_thread_sync`、`after_thread_sync` 的独立和完整上下文。
- `wait::ld`、`wait::st` 的独立和完整上下文。
- 有/无 store wait、有/无显式 fence、CTA group 1/2 的 2×2×2 生命周期矩阵。
- alloc、dealloc、relinquish、mbarrier init/inval 的资源边界。
- O0/O1/O2/O3 四个优化级的可汇编性与完整 case 的核心 SASS 模式。

以下运行时问题不在 95% 覆盖范围之内：

- release/acquire 在真实双线程、双 CTA/cluster 程序中的可见值 litmus test。
- CTA group 2 的 peer CTA 合法 launch、到达关系和死锁检查。
- 描述符、TMEM 地址和 mbarrier 地址在真实 kernel 中的动态有效性。
- 数值正确性、性能、延迟和不同 CUDA/PTX 工具链版本的稳定性。

## 阅读 SASS 时的判断顺序

1. 先找 `UTCHMMA`/`UTC*MMA`，确认 CTA group 和核心异步工作。
2. 找 `UTCBAR*`，确认 MMA/cp/shift completion 是否提交给 mbarrier。不要把它当普通 `MEMBAR`。
3. 找 `SYNCS.PHASECHK*`，确认消费者确实检查 phase。再回到 PTX 判断它是 relaxed 还是 acquire，因为修饰符不一定在单条 SASS 名称中保留。
4. 找 `LDTM`/`STTM` 和 `FENCE.VIEW.ASYNC.T`，判断 TMEM I/O 完成路径。缺少独立 wait 助记符时检查后续依赖和完整上下文。
5. 找 `MEMBAR`/`ERRBAR`/`CGAERRBAR`，但只把它们当当前编译降级见证，不把固定序列外推为 PTX 规范本身。
6. 最后检查 `BAR.SYNC`、dealloc/relinquish 和 mbarrier inval，确认参与线程和资源生命周期闭合。

## 证据入口

- 生成规则：[`../../generate_protocol_layers.py`](../../generate_protocol_layers.py)
- 42 个 case 的清单：[`../../results/protocol-layers/sources/manifest.jsonl`](../../results/protocol-layers/sources/manifest.jsonl)
- 168 次编译与 32 次 SASS 检查报告：[`../../results/protocol-layers/compile_report.json`](../../results/protocol-layers/compile_report.json)
- 官方规范：[NVIDIA PTX ISA 9.3](https://docs.nvidia.com/cuda/parallel-thread-execution/)

# TMA / `cp.async` composed semantic suite

这个目录是独立的 `SEMANTIC_LIFECYCLE` 测试集，不是 `verification/ptx_sources/` 中的
`STATIC_MAPPING` 样例。它不修改也不替代现有的一条 PTX→一段 SASS 的采集证据。

现有 mapping 文件故意隔离单条 PTX，因此不能跨文件组成 TMA、`mbarrier` 或
`cp.async` 的运行时协议。本目录把必要的配套步骤放进同一个 kernel，并通过 CUDA
Driver API 真实执行已由 `ptxas` 编译的 cubin。

## 覆盖的闭环

| 用例 | 所验证的完整链 | 对应的孤立 mapping 片段 | 主机侧判定 |
|---|---|---|---|
| `tma_mbarrier_load_2d` | `mbarrier.init → bar.sync → tensormap acquire + fence.proxy.async → TMA load → arrive.expect_tx(1024) → implicit complete_tx → try_wait loop → shared load` | M01、B01、B03、B07、F01、F04 | 16×16 输入 `1..256` 在 wait 后必须逐元素一致。 |
| `cp_async_group` | `cp.async.ca + cp.async.cg → cp.async.commit_group → cp.async.wait_group 0 → shared load` | M08、M09、M10 | 8 个输入 `u32` 必须逐元素一致。 |
| `tma_bulk_store_2d` | `shared store → fence.proxy.async + tensormap acquire → TMA shared→global bulk_group → bulk.commit_group → bulk.wait_group 0` | M04、M07、F01、F04；补足此前缺失的 bulk wait | 16×16 输出 tile 必须逐元素等于 `0xA5000000 | index`。 |

这三条分别覆盖了不能混用的三种完成机制：mbarrier-based TMA load、classic
`cp.async` group，以及 bulk async-group。特别是 `cp.async.wait_group` **不能**等待
`.bulk_group`；第三条刻意使用 `cp.async.bulk.wait_group 0`。

```text
TMA load:
  initializer → mbarrier.init → CTA publication → tensor-map/async-proxy fences
  → cp.async.bulk.tensor ... complete_tx::bytes → arrive.expect_tx(bytes)
  → try_wait succeeds → consume shared tile

Classic cp.async:
  cp.async.{ca,cg} → cp.async.commit_group → cp.async.wait_group 0 → consume shared words

TMA bulk store:
  fill shared tile → generic/async proxy fence + tensor-map acquire → TMA bulk_group
  → cp.async.bulk.commit_group → cp.async.bulk.wait_group 0 → host checks global tile
```

## 运行

在 B200（`sm_100a`）且 CUDA Toolkit 12.8 或更新版本上运行：

```bash
cd /workspace/PTX_To_SASS/verification/semantic_suite/tma
bash run.sh
```

若 CUDA 12.8 没有挂在 `/usr/local/cuda`，显式指定路径：

```bash
CUDA_HOME=/usr/local/cuda-12.8 bash run.sh
```

默认一次执行 O0 和 O3：每个优化级别都会重新编译三个 composed PTX、保存
`nvdisasm -g` 与 `nvdisasm -gp`，再用同一 host runner 运行并断言结果。也可以只跑一个
优化级别，或先只检查静态可编译性：

```bash
bash run.sh --opt 0
bash run.sh --compile-only --opt all
```

顶层调度或多 GPU 主机可传递同样明确的参数：

```bash
bash run.sh --arch sm_100a --cuda-home /usr/local/cuda-12.8 \
  --device 0 --out-dir /tmp/ptx_to_sass_tma_b200
```

`--compile-only` 只证明工具链接受闭环 PTX，不能替代 GPU 执行验证。真实运行会由
`run_tma_semantic_suite.cpp` 通过 CUDA Driver API：

1. 在 host 使用 `cuTensorMapEncodeTiled` 创建无 swizzle 的 16×16 `u32` tensor map；
2. 把 opaque `CUtensorMap` 拷到 device global memory，并以指针传入 PTX；
3. 加载本目录刚编译的 cubin，启动对应 entry；
4. 同步后校验 scalar、classic copy 输出和 bulk TMA 全部 256 个元素。

默认生成物都在 `build/` 且被忽略；本目录也忽略意外放入的 `*.cubin`、`*.sass` 和
`*.err`。其中包括 `cubin/O0/`、`cubin/O3/`、`sass/O0/`、`sass/O3/`、host runner 和
`runtime_results.txt`。`--out-dir` 可将这些产物移到指定目录。不要把它们混入静态 mapping
的 `verification/cubins` 或 `verification/sass_dumps`；若需要保存 B200 证据，记录工具链、
GPU、命令及文本结果到经过审查的文档，而不是把临时 build 目录当作 mapping 产物。

## 当前验证状态

- B200 runtime validated（2026-07-24）：NVIDIA B200
  `GPU-90518175-3702-4bfe-31c9-578f1592d5d3`，driver `580.159.03`，CUDA / ptxas
  `12.8.93`。三个 composed PTX 在 O0 和 O3 均重新编译、反汇编并经 CUDA Driver API 执行。
- 结果：`tma_mbarrier_load_2d` 的 16×16 tile、`cp_async_group` 的 8 个 `u32`、以及
  `tma_bulk_store_2d` 的全部 256 个元素均通过 host oracle。
- 证据目录：`/workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260724T061600Z_final/tma`。

## 当前刻意未覆盖的 TMA 变体

这三个闭环覆盖 M01、M04、M07、M08、M09、M10 的关键 completion protocol，但不应把
它们外推成 M02–M06 也已运行验证：

| 孤立样例 | 未纳入本轮 runtime 的原因 | 后续正确的验证前提 |
|---|---|---|
| M02 `load_3d` | 当前 host runner 只构造 rank-2 tensor map。 | 新增 rank-3 `CUtensorMap`、3D tile oracle 与同样的 mbarrier completion 链。 |
| M03 multicast load | 需要真实 cluster launch、目标 CTA 的 shared barrier 生命周期和正确 multicast mask。 | 至少两个 CTA 的 cluster kernel；每个目标 CTA 初始化并等待其 barrier。 |
| M05 reduce-add store | 除 bulk async-group 外还需定义 global 初值和 reduction oracle。 | 以已知 destination 初值 + 已知 shared tile 检查逐元素 `add` 结果。 |
| M06 prefetch | 这是 cache-performance hint，不产生可由功能输出确认的数据。 | 单独记录 profiler/timing 实验；不能用普通 correctness kernel 宣称其功能通过。 |

因此，B200 运行通过只意味着本表已经列出的 composed protocol 通过，不意味着所有 TMA
modifiers、cluster multicast 或 prefetch 行为都已验证。

## 有意不做的事

- 不把 init、commit、wait 或 fence 回写进 `ptx_sources/02_tma` 或
  `ptx_sources/03_mbarrier`；那些文件继续只描述各自目标指令的静态 lowering。
- 不运行“缺 wait / 缺 init”的负例。这样的 PTX 可能导致未定义行为或永久等待，不能
  作为稳定的 B200 自动化测试。
- 不把 `cp.async.wait_group` 当成 bulk completion；bulk 路径只使用
  `cp.async.bulk.commit_group` 与 `cp.async.bulk.wait_group`。

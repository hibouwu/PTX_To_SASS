# TMA / `cp.async` composed semantic suite

这个目录是独立的 `SEMANTIC_LIFECYCLE` 测试集，不是 `verification/ptx_sources/` 中的
`STATIC_MAPPING` 样例。它不修改也不替代现有的一条 PTX→一段 SASS 的采集证据。

现有 mapping 文件故意隔离单条 PTX，因此不能跨文件组成 TMA、`mbarrier` 或
`cp.async` 的运行时协议。本目录把必要的配套步骤放进同一个 kernel，并通过 CUDA
Driver API 真实执行已由 `ptxas` 编译的 cubin。

## 覆盖的闭环

| 用例 | 状态 | 所验证的完整链 | 主机侧判定 |
|---|---|---|---|
| `tma_mbarrier_load_2d` | `RUNTIME_PASS` | `mbarrier.init → CTA publication → TMA 2D load → arrive.expect_tx(1024) → complete_tx → try_wait → shared load` | 16×16 输入逐元素一致。 |
| `tma_mbarrier_load_3d` | `RUNTIME_PASS` | 同一 completion 链，rank-3 tensor map 与 `tensor.3d` load，transaction 为 2048 B。 | 16×16×2 输入逐元素一致。 |
| `tma_multicast_cluster_2d` | `RUNTIME_PASS` | 两个 cluster CTA 各自 init/expect_tx 本地 mbarrier → cluster publication → rank 0 发一次 `multicast::cluster`（mask `0b11`）→ 两边各自 wait。 | 两个 CTA 导出的 16×16 tile 都与同一输入一致。 |
| `tma_reduce_add_2d` | `RUNTIME_PASS` | 填 shared tile → async-proxy/tensormap fence → `cp.reduce...add.bulk_group` → bulk commit/wait。 | 每个 global 元素等于已知初值加 `1..256`。 |
| `tma_strided_load_2d` | `RUNTIME_PASS` | rank-2 map 的 logical shape 为 16×16，第二维 physical stride 为 32 个 `u32` → mbarrier completion。 | 跳过每行 16 个 padding 后，输出仍逐元素一致。 |
| `tma_swizzle_roundtrip_2d_32B` | `RUNTIME_PASS` | matching 32B-swizzle map：TMA load → mbarrier wait → TMA store → bulk wait。 | row-major global 输入/输出逐元素一致。 |
| `tma_swizzle_roundtrip_2d_64B` | `RUNTIME_PASS` | matching 64B-swizzle map：TMA load → mbarrier wait → TMA store → bulk wait。 | row-major global 输入/输出逐元素一致。 |
| `tma_swizzle_roundtrip_2d_128B` | `RUNTIME_PASS` | matching 128B-swizzle map：TMA load → mbarrier wait → TMA store → bulk wait。 | row-major global 输入/输出逐元素一致。 |
| `tma_prefetch_2d_execute` | `RUNTIME_EXECUTED` | tensormap acquire → `cp.async.bulk.prefetch.tensor.2d.L2.global`。 | 合法 descriptor 下 kernel 到达并越过该指令；不对 cache residency 或性能作断言。 |
| `cp_async_group` | `RUNTIME_PASS` | `cp.async.ca + cp.async.cg → cp.async.commit_group → cp.async.wait_group 0 → shared load`。 | 8 个输入 `u32` 逐元素一致。 |
| `tma_bulk_store_2d` | `RUNTIME_PASS` | shared store → proxy/tensormap fence → TMA shared→global bulk group → bulk commit/wait。 | 16×16 输出 tile 逐元素等于 `0xA5000000 | index`。 |

`cp.async.wait_group` 不能等待 `.bulk_group`；所有 TMA store/reduce 用例都使用
`cp.async.bulk.commit_group` 与 `cp.async.bulk.wait_group 0`。cluster multicast 由 host
通过 `cuLaunchKernelEx` 指定 `CU_LAUNCH_ATTRIBUTE_CLUSTER_DIMENSION={2,1,1}`，不是普通的
单 CTA launch。

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

默认一次执行 O0 和 O3：每个优化级别都会重新编译本目录全部 composed PTX、保存
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

1. 在 host 用 `cuTensorMapEncodeTiled` 建 rank-2、rank-3、pitched 与 swizzled `u32` tensor map；
2. 把 opaque `CUtensorMap` 拷到 device global memory，并以指针传入 PTX；
3. 普通 case 用 `cuLaunchKernel`，multicast case 用带 2-CTA cluster attribute 的 `cuLaunchKernelEx`；
4. 同步后逐元素检查 load、reduce、layout 与 multicast 输出；prefetch 只检查该指令实际执行。

默认生成物都在 `build/` 且被忽略；本目录也忽略意外放入的 `*.cubin`、`*.sass` 和
`*.err`。其中包括 `cubin/O0/`、`cubin/O3/`、`sass/O0/`、`sass/O3/`、host runner 和
`runtime_results.txt`。`--out-dir` 可将这些产物移到指定目录。不要把它们混入静态 mapping
的 `verification/cubins` 或 `verification/sass_dumps`；若需要保存 B200 证据，记录工具链、
GPU、命令及文本结果到经过审查的文档，而不是把临时 build 目录当作 mapping 产物。

## 当前验证状态

- B200 runtime validated（2026-07-27）：NVIDIA B200
  `GPU-57763773-1c85-4260-7159-cacae400a77d`，driver `580.105.08`，CUDA / ptxas `12.8.93`。
  本目录全部 PTX 在 O0 与 O3 均重新编译、反汇编并经 CUDA Driver API 执行。
- 除 `tma_prefetch_2d_execute` 外，表中每个新用例都有逐元素或精确 scalar oracle，因此标为
  `RUNTIME_PASS`。prefetch 是性能 hint；`RUNTIME_EXECUTED` 只说明它在合法 map 上被发射并完成了
  kernel，不可推出命中率、缓存驻留时间或性能收益。
- swizzle 三例验证的是 matching map 的 **logical round-trip**。它们证明 TMA 读写路径与 map
  一致，不单独导出 shared-memory 的 physical permutation；不要据此把特定 bank-address permutation
  当成已经测量的事实。
- 最新统一证据：`artifacts/b200_20260727T093435Z_full_semantic_final/tma/`。该轮 `run_all.sh`
  对 2D/3D、reduce、pitched layout、三种 swizzle、2-CTA multicast、classic/bulk completion 都得到了
  O0/O3 `RUNTIME_PASS`；prefetch 在 O0/O3 都为 `RUNTIME_EXECUTED`。
- 可复现实验命令：

```bash
cd /workspace/PTX_To_SASS
CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/tma/run.sh --opt all \
  --out-dir verification/semantic_suite/artifacts/<new-b200-artifact>/tma
```

## 有意不做的事

- 不把 init、commit、wait 或 fence 回写进 `ptx_sources/02_tma` 或
  `ptx_sources/03_mbarrier`；那些文件继续只描述各自目标指令的静态 lowering。
- 不运行“缺 wait / 缺 init”的负例。这样的 PTX 可能导致未定义行为或永久等待，不能
  作为稳定的 B200 自动化测试。
- 不把 `cp.async.wait_group` 当成 bulk completion；bulk 路径只使用
  `cp.async.bulk.commit_group` 与 `cp.async.bulk.wait_group`。

# B200 mbarrier composed semantic suite

此目录是独立的**运行时语义**测试，不替代也不修改 `verification/ptx_sources/03_mbarrier/` 中的
`STATIC_MAPPING` 样例。后者用于回答“一条 PTX 如何 lower 到 SASS”；本目录验证完整协议。CTA
case 在 `mbarrier_semantic.ptx`，cluster/remote case 在
`mbarrier_cluster_remote_semantic.ptx`。

## 覆盖内容

| Kernel | 同一 kernel 中的闭环 | Host 断言 |
|---|---|---|
| `test_mbarrier_arrive_wait` | 单线程 `init(32)` → CTA 发布 → 32 个 `arrive.release` → 独立 control-mbarrier 确认所有 arrivals 已发出 → lane 0 `try_wait.acquire` → 消费 shared 数据 → `inval` | lane 0 在 acquire 后读到 `1..32`，和为 `528` |
| `test_mbarrier_expect_tx_complete_tx` | 单线程 `init(32)` → `expect_tx(1)` → 32 个 `arrive.release` → control-mbarrier 确认 arrivals → `test_wait` 仍未完成 → `complete_tx(1)` → lane 0 `try_wait.acquire` → `inval` | `out[0] == 1` 表示 complete_tx 前 wait 为 false；`out[1] == 0xC0DEC0DE` 表示完成后 wait 成功 |
| `test_mbarrier_arrive_expect_tx_complete_tx` | 单线程 `init(32)` → lane 0 `arrive.expect_tx(1)` → 其余 31 个 `arrive.release` → control-mbarrier 确认 32 次 arrival → `test_wait` 仍未完成 → `complete_tx(1)` → `try_wait.acquire` → `inval` | `out[0] == 1` 表示 transaction 未完成时 wait 为 false；`out[1] == 0xB03B03B0` 表示 `complete_tx` 后 wait 成功 |
| `test_mbarrier_arrive_drop_next_phase` | 单线程 `init(32)` → phase 0: 31 个 `arrive` + lane 31 `arrive_drop` → phase 1: 仅余下 31 个 `arrive` → lane 0 `try_wait.acquire` → `inval` | `out[0] == 0x0A441D04`；phase 1 只在 `arrive_drop` 已将下一 phase 的 participant count 从 32 改成 31 时才会完成 |
| `test_mbarrier_multi_phase_reuse` | 单线程 `init(32)` 一次 → 连续四个 phase；每 phase 都是 32 个 `arrive.release` → lane 0 `try_wait.acquire` → 读 shared payload → CTA barrier 保护下一 phase 的重用 → 最后 `inval` | 四个输出依次为 `528`、`3728`、`6928`、`10128`；证明同一个 barrier 在未重新 `init` 的情况下持续 re-arm |
| `test_mbarrier_cluster_remote` | CTA 0 `init(64)` → `fence.mbarrier_init.release.cluster` → cluster 发布初始化 → CTA 1 写 local shared payload → 64 个 cluster thread 远程 `arrive.release.cluster.shared::cluster` 到 CTA 0 的 barrier → CTA 0 `try_wait.parity.acquire.cluster` → `ld.shared::cluster` 读取 CTA 1 payload → 最后 cluster barrier 与 `inval` | `out[0] == 0xC1A57E01`，`out[1] == 0xC1A57E02`；验证 remote arrival、cluster-scope acquire 与 DSMEM 读取 |

第二个 kernel 不使用 TMA、MMA 或 `tcgen05`。它只验证 mbarrier 自身的 transaction count：arrival
count 已归零时，只要 outstanding transaction 仍为 1，phase 就不能完成；`complete_tx(1)` 后才可
通过 wait。第三个 kernel 保留同一不变量，但把 leader 的 arrival 与 transaction 建立合为
`mbarrier.arrive.expect_tx`，直接为静态 B03 目标提供完整运行时协议。

连续复用 case 的 CTA barrier 位于 leader 已完成 acquire、读完本 phase payload 之后，只防止下一
phase 的 store 覆盖仍在读取的数据；payload 的可见性边仍是本 phase 的
`arrive.release → try_wait.acquire`。cluster case 的第一个 `barrier.cluster` 只发布 CTA 0 初始化的
barrier；CTA 1 写 payload 后到 CTA 0 读 DSMEM 前没有 cluster barrier。CTA 1 lane 0 的 store 由它的
`mbarrier.arrive.release.cluster.shared::cluster` 发布，CTA 0 的
`mbarrier.try_wait.parity.acquire.cluster.shared::cta` 消费，再执行 `ld.shared::cluster`。结尾的
cluster barrier 只保证 CTA 1 的 shared allocation 在远程读取完成前仍然存活。

## B200 CUDA 12.8 执行

在项目根目录运行：

```bash
CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/mbarrier/run.sh --arch sm_100a
```

该命令会：

1. 以 `ptxas -O0` 和 `ptxas -O3` 编译同一份 composed PTX；
2. 保存 `nvdisasm -g` 和 `nvdisasm -gp` 证据；
3. 用 CUDA Driver API 加载每个 cubin：CTA PTX 固定发射 `<<<1, 32>>>`；cluster PTX 用
   `cuLaunchKernelEx` 发射 `grid=2, block=32, clusterDim=(2,1,1)`；
4. 对五个 CTA kernel 与一个 cluster kernel 的输出断言并在任一失败时返回非零。

顶层 orchestrator 可将结果定向到独立目录，也可选择 B200 的 device ordinal：

```bash
bash verification/semantic_suite/mbarrier/run.sh \
  --cuda-home /usr/local/cuda-12.8 --arch sm_100a --device 0 \
  --out-dir /tmp/ptx_to_sass_mbarrier
```

`--out-dir` 下会创建 `build/`、`cubin/`、`sass/`；脚本只覆盖本 suite 已知的产物名。

只做编译/反汇编、不连接 GPU 时：

```bash
CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/mbarrier/run.sh --arch sm_100a --compile-only
```

生成产物在 `build/`、`cubin/`、`sass/`，均被本目录 `.gitignore` 排除。不要将这些产物混入静态
mapping 的 `verification/cubins` 或 `verification/sass_dumps`。

## B200 运行记录（2026-07-27）

- GPU：NVIDIA B200，UUID `GPU-57763773-1c85-4260-7159-cacae400a77d`；driver `580.105.08`。
- 工具链：CUDA / ptxas `12.8.93`，`sm_100a`；两份 PTX 都以 O0、O3 重新编译、反汇编并由 CUDA Driver API 执行。
- 最新统一命令：`env CUDA_HOME=/usr/local/cuda-12.8 CUTLASS_ROOT=/workspace/PTX_To_SASS/third_party/cutlass timeout 3600s bash verification/semantic_suite/run_all.sh --arch sm_100a --cuda-home /usr/local/cuda-12.8 --device 0 --out-dir verification/semantic_suite/artifacts/b200_20260727T093435Z_full_semantic_final --keep-going`。
- 证据目录：`/workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260727T093435Z_full_semantic_final/mbarrier/`。
- 结果：O0/O3 下五个 CTA oracle 和 cluster/remote oracle 全部通过。连续复用四个 sum 为
  `528, 3728, 6928, 10128`；remote payload 为 `0xC1A57E01`，protocol status 为 `0xC1A57E02`。

## 设计约束

- `mbarrier_semantic.ptx` 的五个 entry 都只能用一个 `32 x 1 x 1` CTA 启动。`mbarrier.init` 的 expected arrival count 与此
  完全一致；改变 block size 会让语义测试失效。
- `mbarrier_cluster_remote_semantic.ptx` 必须用一个 `2 x 1 x 1` CTA cluster、每 CTA 32 个线程启动。
  该 PTX 的 `.reqnctapercluster 2,1,1` 和 host 端 `CU_LAUNCH_ATTRIBUTE_CLUSTER_DIMENSION` 都是协议的一部分；
  普通 `cuLaunchKernel` 或两个独立 CTA 不能替代它。
- 对带 payload 可见性 oracle 的普通 case，写入后到 leader acquire/读取前没有 `bar.sync`；
  control-mbarrier 显式使用 `arrive.relaxed` / `try_wait.relaxed`，只确认所有主 barrier 的 arrive
  已执行，刻意不把它作为 payload 的可见性边。`arrive_drop` case 的 CTA barrier 只保护 phase 进度，
  multi-phase case 的 CTA barrier 只在 leader 消费完 payload 后保护下一轮 reuse。读取
  `smem_values` 前的唯一 acquire 仍是主 barrier 的 `try_wait.acquire`，因此普通测试确实覆盖
  release→acquire 的 mbarrier 可见性关系。
- `mbarrier.expect_tx` 必须发生在任意 arrival 之前，因此第二个 kernel 在它后面保留了 CTA barrier。
- 单个 `ptx_sources/03_mbarrier/B0x_*.ptx` 不能跨文件拼成这种测试：批处理会将每个文件编成不同的
  cubin/kernel，其 shared barrier 不是同一个对象；cluster case 还需要同一次 cluster launch 中的
  DSMEM address map。

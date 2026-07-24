# B200 mbarrier composed semantic suite

此目录是独立的**运行时语义**测试，不替代也不修改 `verification/ptx_sources/03_mbarrier/` 中的
`STATIC_MAPPING` 样例。后者用于回答“一条 PTX 如何 lower 到 SASS”；本目录用于回答“把 mbarrier
的完整生命周期放进同一个可运行 kernel 后，协议是否成立”。

## 覆盖内容

| Kernel | 同一 kernel 中的闭环 | Host 断言 |
|---|---|---|
| `test_mbarrier_arrive_wait` | 单线程 `init(32)` → CTA 发布 → 32 个 `arrive.release` → 独立 control-mbarrier 确认所有 arrivals 已发出 → lane 0 `try_wait.acquire` → 消费 shared 数据 → `inval` | lane 0 在 acquire 后读到 `1..32`，和为 `528` |
| `test_mbarrier_expect_tx_complete_tx` | 单线程 `init(32)` → `expect_tx(1)` → 32 个 `arrive.release` → control-mbarrier 确认 arrivals → `test_wait` 仍未完成 → `complete_tx(1)` → lane 0 `try_wait.acquire` → `inval` | `out[0] == 1` 表示 complete_tx 前 wait 为 false；`out[1] == 0xC0DEC0DE` 表示完成后 wait 成功 |
| `test_mbarrier_arrive_expect_tx_complete_tx` | 单线程 `init(32)` → lane 0 `arrive.expect_tx(1)` → 其余 31 个 `arrive.release` → control-mbarrier 确认 32 次 arrival → `test_wait` 仍未完成 → `complete_tx(1)` → `try_wait.acquire` → `inval` | `out[0] == 1` 表示 transaction 未完成时 wait 为 false；`out[1] == 0xB03B03B0` 表示 `complete_tx` 后 wait 成功 |
| `test_mbarrier_arrive_drop_next_phase` | 单线程 `init(32)` → phase 0: 31 个 `arrive` + lane 31 `arrive_drop` → phase 1: 仅余下 31 个 `arrive` → lane 0 `try_wait.acquire` → `inval` | `out[0] == 0x0A441D04`；phase 1 只在 `arrive_drop` 已将下一 phase 的 participant count 从 32 改成 31 时才会完成 |

第二个 kernel 不使用 TMA、MMA 或 `tcgen05`。它只验证 mbarrier 自身的 transaction count：arrival
count 已归零时，只要 outstanding transaction 仍为 1，phase 就不能完成；`complete_tx(1)` 后才可
通过 wait。第三个 kernel 保留同一不变量，但把 leader 的 arrival 与 transaction 建立合为
`mbarrier.arrive.expect_tx`，直接为静态 B03 目标提供完整运行时协议。

## B200 CUDA 12.8 执行

在项目根目录运行：

```bash
CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/mbarrier/run.sh --arch sm_100a
```

该命令会：

1. 以 `ptxas -O0` 和 `ptxas -O3` 编译同一份 composed PTX；
2. 保存 `nvdisasm -g` 和 `nvdisasm -gp` 证据；
3. 用 CUDA Driver API 加载每个 cubin，固定发射 `<<<1, 32>>>`；
4. 对四个 kernel 的输出断言并在任一失败时返回非零。

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

## B200 运行记录（2026-07-24）

- GPU：NVIDIA B200，UUID `GPU-90518175-3702-4bfe-31c9-578f1592d5d3`；driver `580.159.03`。
- 工具链：CUDA / ptxas `12.8.93`，`sm_100a`；O0 和 O3 均重新编译、反汇编并通过 CUDA Driver API 执行。
- 证据目录：`/workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260724T061600Z_final/mbarrier`。
- 结果：四个 host oracle 均在 O0/O3 通过：普通 arrive/wait 的和为 `528`，`expect_tx`、
  `arrive.expect_tx` 和 `arrive_drop` 的 phase/accounting 断言也全部成立。

## 设计约束

- 四个 entry 都只能用一个 `32 x 1 x 1` CTA 启动。`mbarrier.init` 的 expected arrival count 与此
  完全一致；改变 block size 会让语义测试失效。
- `bar.sync` 仅在写入任何测试 payload 之前发布两个已初始化 barrier，并在第二个测试中保证
  `expect_tx` 先于任意 arrival。**arrival 之后没有 `bar.sync`**；control-mbarrier 显式使用
  `arrive.relaxed` / `try_wait.relaxed`，只确认所有主 barrier 的 arrive 已执行，刻意不把它作为
  payload 的可见性边。读取 `smem_values` 前的唯一 acquire 是主 barrier 的 `try_wait.acquire`，因此
  普通测试确实覆盖 release→acquire 的 mbarrier 可见性关系。
- `mbarrier.expect_tx` 必须发生在任意 arrival 之前，因此第二个 kernel 在它后面保留了 CTA barrier。
- 单个 `ptx_sources/03_mbarrier/B0x_*.ptx` 不能跨文件拼成这种测试：批处理会将每个文件编成不同的
  cubin/kernel，其 shared barrier 不是同一个对象。

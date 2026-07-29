# Composed semantic suite

这个目录是对 `verification/ptx_sources/` 的**补充**，不是替代。

- `ptx_sources/` 保持 `STATIC_MAPPING`：一个 PTX 目标动作一个最小 kernel，用于归因
  PTX 核心动作到 SASS 核心 opcode。
- `semantic_suite/` 保持 `COMPOSED_SEMANTIC`：把初始化、producer、commit、wait、
  fence、consumer 和资源回收写在**同一个 kernel** 中，用可观察输出验证运行时协议。

因此，semantic suite 的额外 SASS 绝不计入静态映射的一对一或一对多统计。

## 覆盖范围

| 子目录 | 协议 | 验证等级 |
|---|---|---|
| `mbarrier/` | CTA arrive/transaction/drop、连续 phase reuse，以及 cluster remote arrive → acquire → DSMEM read | `RUNTIME_VALIDATED_B200`（2026-07-27，O0/O3） |
| `tma/` | 2D/3D load、reduce-add、pitched layout、32/64/128B swizzle、2-CTA multicast、classic/bulk `cp.async` 与 prefetch | `RUNTIME_VALIDATED_B200`（2026-07-27，O0/O3） |
| `tcgen05/` | raw PTX 生命周期，加上 CuTe 生成真实 descriptor 的 F16/BF16/TF32 CG1 与 F16 CG2 numerical GEMM | `RUNTIME_VALIDATED_B200`（2026-07-27，O0/O3） |

`RUNTIME_CAPABLE` 表示测试设计为在 B200 上执行，**不代表尚未保存的本地或远端产物已经
通过**。只有登记为 `RUNTIME_VALIDATED_B200` 后才能报告 B200 runtime pass。每个子目录的
README 必须记录实际运行的 GPU、driver、CUDA/PTXAS 版本、命令和结果。

`tma_prefetch_2d_execute` 的等级是 `RUNTIME_EXECUTED`：它证明有效 tensor map 到达了 prefetch
指令，不声称 cache residency 或性能收益。

## B200 运行原则

```bash
export CUDA_HOME=/usr/local/cuda-12.8
cd verification/semantic_suite/<component>
# 具体命令见该 component 的 README。
```

`tcgen05/run.sh` 还需要固定的 CUTLASS `v4.2.1`
(`f3fde58372d33e9a5650ba7b80fc48b3b49d40c8`) checkout；默认位置是
`<repo>/third_party/cutlass`，可用 `CUTLASS_ROOT` 覆盖。

所有构建输出应放在 semantic suite 自己忽略的 `build/`、`cubin/`、`sass/` 或一次性
`--out-dir` 中；不要写入 `verification/cubins/`、`verification/sass_dumps/`、
`verification/sass_ptx_dumps/` 或 `verification/results/`。

## 判定规则

一个测试只有同时满足下列条件，才能写为 runtime 通过：

1. 在 B200 (`sm_100a`) 上由 CUDA 12.8 编译并成功加载；
2. host runner 的可观察输出与预期一致；
3. 保存 O0/O3 的 `nvdisasm -g` 和 `-gp` 证据；
4. README 写明运行环境和原始结果。

若只通过本机 `ptxas` 编译，它只能写为 `STRUCTURAL_COMPILE_ONLY`。

## 统一入口

顶层入口按固定顺序调度 `mbarrier`、`tma`、`tcgen05` 三个 runtime family。`tcgen05` 会先保留
raw-PTX structural evidence，再运行 CuTe 的真实 descriptor numerical cases；两层证据都放在
本次 `tcgen05/` 输出下。

```bash
# 在 B200 / CUDA 12.8 上执行全部可用 family，并保存统一调度日志。
CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/run_all.sh

# 只做编译和反汇编；不会调用 CUDA Driver API launch。
CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/run_all.sh --compile-only

# 例如跳过 tcgen05，或只运行一个 family。
bash verification/semantic_suite/run_all.sh --skip-tcgen05
bash verification/semantic_suite/run_all.sh --family mbarrier
```

默认日志目录是 `semantic_suite/artifacts/<UTC timestamp>/`；它被 Git 忽略。传入
`--out-dir DIR` 时，每个 family 都会得到各自的 `DIR/<family>/`，而调度日志和摘要仍在
`DIR/`。`tcgen05` 的 `structural/` 与 `runtime/` 都在 `DIR/tcgen05/` 下，因此一次采集不会覆盖
另一次的证据。

每个 runtime family 的 `run.sh` 应接受以下 ABI：

```text
--arch sm_100a
--compile-only
--out-dir <family-output-dir>
--device <ordinal>
--cuda-home <toolkit-root>
```

新增 family 前应先实现这个 ABI，并在 `STATUS.md` 注册其验证等级。`tcgen05/run.sh` 也遵守该 ABI；
`run_structural.sh` 仍可单独用于 raw-PTX lifecycle 采集。

`STATUS.md` 是人工维护的证据状态表；顶层每次运行生成的 `run-summary.tsv` 只是本次
命令的执行记录，不能替代 B200 证据登记。

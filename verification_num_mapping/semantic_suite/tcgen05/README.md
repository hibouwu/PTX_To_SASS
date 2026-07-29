# B200 tcgen05 composed semantic suite

`verification/ptx_sources/01_tcgen05/` 是 **STATIC_MAPPING** 证据：一个 PTX 文件只看一条
指令怎样被 `ptxas` lower。本目录做另一件事：把真实 shared-memory descriptor、TMEM、completion
barrier、load/wait/dealloc 放进可运行的 GEMM，再用 host reference 检查结果。

这里不从 host 传入 A/B descriptor 或 `idesc`。这类值与 CTA 内 shared-memory layout 绑定，随手构造
一个 bit pattern 即使被 PTX 接受，也不能说明 `tcgen05.mma` 正确执行。

## 两层证据

- `run_structural.sh`：保留 raw PTX 生命周期。它只编译和反汇编，不能 launch。
- `run.sh`：先跑 structural，再编译、反汇编并运行下面的 CuTe numerical cases。`run.sh` 是顶层
  semantic-suite 应调用的入口。

| case | CuTe source | MMA / descriptor path | GEMM problem | oracle |
| --- | --- | --- | --- | --- |
| `f16_cg1` | CUTLASS tutorial `01_mma_sm100.cu` | `SM100_MMA_F16BF16_SS`, CTA group 1, 128x256x16 | 512x1024x256 | CPU `reference_gemm` |
| `bf16_cg1` | tutorial 01 的受限 BF16 variant | `SM100_MMA_F16BF16_SS`, CTA group 1, 128x256x16 | 256x512x128 | CPU `reference_gemm` |
| `tf32_cg1` | tutorial 01 的受限 TF32 variant | `SM100_MMA_TF32_SS`, CTA group 1, 128x256x8 | 256x512x128 | CPU `reference_gemm` |
| `f16_cg2` | CUTLASS tutorial `04_mma_tma_2sm_sm100.cu` | `SM100_MMA_F16BF16_2x1SM_SS`, CTA group 2, 256x256x16 | 512x1024x256 | CPU `reference_gemm` |

`f16_cg2` 同时经过 2SM cluster 和 TMA/multicast 的 tutorial 路径。它不是把同一个 CG1 case 改个
launch 参数：MMA instruction shape 从 128x256x16 变为 256x256x16。

BF16 和 TF32 variant 在运行目录的 `runtime/generated/` 中生成；它们只替换 tutorial 01 的 A/B
element type 与 `TiledMMA` atom，并插入相应 CUTLASS type header。`make_fragment_A/B`、instruction
descriptor、shared-memory swizzle、TMEM allocator、completion barrier、`tcgen05.ld/wait`、以及 host
reference 都仍是固定版本的 upstream CuTe 实现。脚本会检查替换后的 atom 名称，避免在上游源变化后
静默生成未知代码。

TF32 case 使用 tutorial 原本的整数值初始化（每个输入在 `[-2, 2]`），这些值可由 TF32 精确表示，
所以 `reference_gemm` 可以做零误差比较。它验证 descriptor、instruction shape、TMEM 生命周期和结果
路径；它不是测量一般浮点输入下的 TF32 舍入误差上界。

## 运行

这套 runtime case 固定使用 **CUTLASS v4.2.1**，commit
`f3fde58372d33e9a5650ba7b80fc48b3b49d40c8`。B200 收集机的默认位置是
`/workspace/PTX_To_SASS/third_party/cutlass`；也可以用 `CUTLASS_ROOT` 或 `--cutlass-root` 覆盖。

```bash
# 首次准备固定依赖；third_party 不应作为本仓库的采集证据提交。
git clone --depth 1 --branch v4.2.1 https://github.com/NVIDIA/cutlass.git \
  /workspace/PTX_To_SASS/third_party/cutlass

CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/tcgen05/run.sh \
  --out-dir verification/semantic_suite/artifacts/b200_<UTC>/tcgen05
```

常用选项：

```bash
# 只采集 O0/O3 cubin + SASS，不 launch numerical kernels。
bash verification/semantic_suite/tcgen05/run.sh --compile-only

# 指定 CUDA-visible device 和非默认的 pinned checkout。
bash verification/semantic_suite/tcgen05/run.sh \
  --device 0 --cutlass-root /workspace/PTX_To_SASS/third_party/cutlass
```

每个 case 都会以 `nvcc -O0 -Xptxas=-O0` 和 `nvcc -O3 -Xptxas=-O3` 单独生成 executable、cubin、
`nvdisasm -g`、`nvdisasm -gp`。仅当该 optimization 的运行日志包含 CUTLASS 的
`Execution is successful.`，它才写入 `runtime/summary.tsv` 为 `RUNTIME_PASS`。

输出目录结构：

```text
tcgen05/
  structural/{cubin,sass}/       # raw PTX 生命周期结构证据
  runtime/
    bin/                         # 每个 case 的 O0/O3 host executable
    cubin/                       # 每个 case 的 O0/O3 cubin
    sass/                        # nvdisasm -g 和 -gp
    generated/                   # BF16/TF32 的受限 tutorial variant
    logs/                         # build、cubin、host oracle logs
    summary.tsv
```

CUDA 12.8 / CUTLASS v4.2.1 的 tutorial CMake target 在这台 B200 image 上没有把
`tools/util/include` 加到 include path。`run.sh` 不依赖该 target，而是显式加入这条上游所需的 include
path 后直接调用 `nvcc`；这不改变 tutorial 的 device-side descriptor construction。

## B200 record — 2026-07-27

- GPU：NVIDIA B200，UUID `GPU-57763773-1c85-4260-7159-cacae400a77d`，driver `580.105.08`，CC 10.0。
- Toolchain：CUDA / ptxas `12.8.93`，CUTLASS `v4.2.1`
  (`f3fde58372d33e9a5650ba7b80fc48b3b49d40c8`)。
- Latest unified evidence：`artifacts/b200_20260727T093435Z_full_semantic_final/tcgen05/`。
  首次独立采集保留在 `artifacts/b200_20260727T092000Z_tcgen05_runtime/`。
- `run_structural.sh` 的 raw PTX lifecycle 在 O0/O3 都通过；四个 numerical case 的 O0/O3 共 8 次
  host oracle 也全部通过，日志均为 `Relative error: 0.000000e+00`。

`nvdisasm -gp` 中的 `UTCHMMA` 数量可作为本次编译产物的快速索引：CG1 的 F16/BF16/TF32 分别为
O0 4 条、O3 8 条；CG2 F16 为 O0 12 条、O3 24 条。这是整个 CuTe GEMM kernel 的 SASS 数量，不能
倒推为某一条 PTX 的静态 1:N mapping；静态 mapping 仍以 `ptx_sources/01_tcgen05/` 为准。

## Raw PTX lifecycle retained for mapping

`tcgen05_mma_lifecycle_structural.ptx` 仍是 launch 禁止的结构样例：

```text
init → alloc → one-thread mma → commit → mbarrier wait
     → CTA handoff → fence → collective ld → wait::ld
     → dealloc → relinquish_alloc_permit → mbarrier.inval
```

其 `p_smem_desc_a`、`p_smem_desc_b`、`p_idesc` 参数只是为了把 PTX/SASS 生命周期固定下来，绝不作为
runtime descriptor ABI。真正运行的 case 由 CuTe 根据 A/B shared-memory tensor、swizzle、MMA atom
和 TMEM fragment 生成这些 operand。相关 issue granularity 和 memory-consistency 语义见 NVIDIA
[PTX ISA 8.7 tcgen05 section](https://docs.nvidia.com/cuda/archive/12.8.0/parallel-thread-execution/index.html)。

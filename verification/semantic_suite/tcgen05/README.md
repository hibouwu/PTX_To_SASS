# B200 tcgen05 composed lifecycle suite

`verification/ptx_sources/01_tcgen05/` 保持为 **STATIC_MAPPING** 证据：每个文件只回答一条
PTX 如何由 `ptxas` lower 到 SASS。本目录是独立的 composed semantic suite，不修改、也不混入那些
单指令样例。

## 当前状态：`STRUCTURAL_COMPILE_ONLY`

`tcgen05_mma_lifecycle_structural.ptx` 把下列生命周期写进**同一个** PTX entry：

```text
单线程 mbarrier.init(1)
  → 全 warp tcgen05.alloc(32 columns)
  → 单线程 tcgen05.mma
  → 单线程 tcgen05.commit(...mbarrier::arrive::one)
  → 单线程 mbarrier.try_wait 循环
  → CTA handoff
  → 全 warp tcgen05.fence::after_thread_sync
  → 全 warp tcgen05.ld + tcgen05.wait::ld
  → 全 warp tcgen05.dealloc + relinquish_alloc_permit
  → 全 warp quiescence + 单线程 mbarrier.inval
```

这是真实 PTX 8.7 / `sm_100a` 的编译和反汇编结构测试，但**不是**数值正确性测试，且本目录没有
launch runner。不要以任意 host 参数启动该 entry。

原因是 `tcgen05.mma` 的 A/B operand 是描述本 CTA shared memory 布局的硬件 descriptor，`p_idesc`
也是匹配 `kind::tf32`、shape、layout 的 instruction descriptor。它们不能由 host 随意伪造；错误的
descriptor、未初始化 shared-memory 输入或错误的 layout 都会使执行无定义。`p_sink` 仅用于让
`tcgen05.ld` 在 SASS 中保持可见，写出的值不是 pass/fail 结果。

这一区分是刻意的：本 suite 验证“缺失的 commit/wait/fence/dealloc 指令能否同处一个可编译控制流”，
不把“`ptxas` 接受 raw descriptor”误报为“B200 算出了正确矩阵”。

## B200 CUDA 12.8 结构验证

在 B200 上运行：

```bash
CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/tcgen05/run_structural.sh --arch sm_100a
```

它会以 `ptxas -O0` 和 `ptxas -O3` 编译，再以 `nvdisasm -g/-gp` 反汇编，并断言每个版本至少含有：

| 生命周期阶段 | 预期 SASS 类别 |
|---|---|
| TMEM allocation | `UTCATOMSWS.FIND_AND_SET.ALIGN` |
| MMA producer | `UTCHMMA` |
| completion tracking | `UTCBAR` |
| mbarrier polling | `SYNCS.PHASECHK...TRYWAIT` |
| collective TMEM load | `LDTM` |
| TMEM deallocation | `UTCATOMSWS.AND` |
| allocation-permit relinquish | `UVIRTCOUNT.DEALLOC.SMPOOL` |
| mbarrier 生命周期关闭 | `SYNCS.CCTL.IV` |

`tcgen05.wait::ld` 也会由脚本直接检查 PTX 源码，但不把它绑定到一个固定的 SASS mnemonic：当前
工具链会把它 lower 为相邻的 warp-ordering 指令（O0）或 O3 的 `NOP`。因此这里的结构证据是
“该 wait PTX 存在且 `ptxas` 接受它”，而不是声称某条独立 SASS 必然等于 `wait::ld`。

默认生成的 cubin 和 SASS 位于本目录 `build/`，已由 `.gitignore` 排除。要为每次采集保留独立证据，
可传入一个新的输出目录：

```bash
CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/tcgen05/run_structural.sh \
  --arch sm_100a --out-dir /tmp/ptx_to_sass_tcgen05_run
```

此时产物位于该目录的 `cubin/`、`sass/` 下。无论哪种方式，它们都不应覆盖
`verification/cubins`、`verification/sass_dumps` 或 STATIC_MAPPING 产物。

## B200 结构验证记录（2026-07-24）

- GPU：NVIDIA B200，UUID `GPU-90518175-3702-4bfe-31c9-578f1592d5d3`；driver `580.159.03`。
- 工具链：CUDA / ptxas `12.8.93`，`sm_100a`。O0 和 O3 都完成编译与 `nvdisasm -g/-gp`，并通过
  生命周期 PTX/SASS marker 检查。
- 证据目录：`/workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260724T061600Z_final/tcgen05`。
- 结论仍为 `STRUCTURAL_COMPILE_ONLY`：没有 launch 该 raw-descriptor kernel，未对 MMA 数值正确性作出声明。

## PTX 语义约束

- `.reqntid 32,1,1` 强制一个完整 warp。`tcgen05.alloc`、`dealloc`、`ld` 和 `wait::ld` 的 `.sync.aligned`
  形式需要该 warp 的所有 lane 以一致 operand 参与。
- `tcgen05.mma.cta_group::1` 和 `tcgen05.commit.cta_group::1` 有单线程 issue granularity，所以只有
  lane 0 发行它们；mbarrier 的 expected-arrival count 因而是 1。
- `tcgen05.commit` 追踪同一线程此前的 MMA，完成时对 mbarrier 执行 `arrive::one`。等待成功后才让全 warp
  进入 `fence::after_thread_sync → ld`；`ld` 之后仍必须有 `wait::ld`，才能在 `dealloc` 前退休该异步 load。
- `fence.proxy.async.shared::cta` 是未来 device-side wrapper 将 generic shared-memory 输入交给 async
  proxy 所需的结构位置；它本身不填充 A/B 数据，也不构造 descriptor。

上述 ordering 与 issue-granularity 依据 NVIDIA 的 [PTX ISA 8.7 tcgen05 memory-consistency section](https://docs.nvidia.com/cuda/archive/12.8.0/parallel-thread-execution/index.html)。

## 升级为可运行数值测试所需的工作

要把本例从 structural suite 升级为 B200 runtime test，必须额外实现经过审查的 device-side CUDA/CuTe
wrapper，而不是传入猜测的 raw 值。该 wrapper 至少应：

1. 在此 CTA 的 shared memory 中初始化已知 A/B tile，并按实际 layout 构造 A/B descriptor；
2. 为同一 MMA shape/type 生成合法 `idesc`，并检查 tile、swizzle、alignment 与 allocated TMEM range；
3. 固定 `<<<1, 32>>>`，保证唯一 MMA issuer 与全 warp `ld/wait` participation；
4. 把 `tcgen05.ld` 的结果写出，并由 host 与独立 reference 结果比较；
5. 在 O0、O3 都通过后，才标记为 `RUNTIME_VALIDATED_B200`。

在这些条件满足前，本目录所有成功信息都只能解读为 **PTX/SASS 生命周期结构完整**，不能解读为 MMA
数值功能已在 B200 验证。

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
| `mbarrier/` | `init → arrive/expect_tx → complete_tx → wait → consume → inval` | `RUNTIME_VALIDATED_B200`（2026-07-24，O0/O3） |
| `tma/` | TMA load 的 mbarrier completion、classic `cp.async` group、bulk async-group | `RUNTIME_VALIDATED_B200`（2026-07-24，O0/O3） |
| `tcgen05/` | TMEM 生命周期与 `producer → commit → wait → fence → ld → wait::ld → dealloc → relinquish → inval` 结构 | 先做结构/编译验证；只有具备真实 descriptor 与结果 oracle 后才标为 runtime |

`RUNTIME_CAPABLE` 表示测试设计为在 B200 上执行，**不代表尚未保存的本地或远端产物已经
通过**。只有登记为 `RUNTIME_VALIDATED_B200` 后才能报告 B200 runtime pass。每个子目录的
README 必须记录实际运行的 GPU、driver、CUDA/PTXAS 版本、命令和结果。

## B200 运行原则

```bash
export CUDA_HOME=/usr/local/cuda-12.8
cd verification/semantic_suite/<component>
# 具体命令见该 component 的 README。
```

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

顶层入口会按固定顺序调度三个 canonical family：`mbarrier`、`tma`、`tcgen05`。
前两个 family 是可执行的 runtime suite；`tcgen05` 当前只有结构验证脚本，顶层会将其
结果单独标为 `STRUCTURAL_COMPILE_ONLY`，不会把它计入 runtime PASS。

```bash
# 在 B200 / CUDA 12.8 上执行全部可用 family，并保存统一调度日志。
CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/run_all.sh

# 只做编译和反汇编；不会调用 CUDA Driver API launch。
CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/run_all.sh --compile-only

# 例如跳过尚未具备数值 oracle 的 tcgen05，或只运行一个 family。
bash verification/semantic_suite/run_all.sh --skip-tcgen05
bash verification/semantic_suite/run_all.sh --family mbarrier
```

默认日志目录是 `semantic_suite/artifacts/<UTC timestamp>/`；它被 Git 忽略。传入
`--out-dir DIR` 时，每个 family 都会得到各自的 `DIR/<family>/`，而调度日志和摘要仍在
`DIR/`。`tcgen05` 仍只报告 structural evidence，但它的 cubin/SASS 也会放在
`DIR/tcgen05/`，因此一次采集不会覆盖另一次的证据。

每个 runtime family 的 `run.sh` 应接受以下 ABI：

```text
--arch sm_100a
--compile-only
--out-dir <family-output-dir>
--device <ordinal>
--cuda-home <toolkit-root>
```

新增 family 前应先实现这个 ABI，并在 `STATUS.md` 注册其验证等级。tcgen05 是唯一刻意的
runtime 例外：它由 `run_structural.sh` 调度，不会 launch kernel，但接受 `--arch` 和
`--out-dir` 来保存结构证据。

`STATUS.md` 是人工维护的证据状态表；顶层每次运行生成的 `run-summary.tsv` 只是本次
命令的执行记录，不能替代 B200 证据登记。

# SASS 调度模型提取与控制位解码 · 操作手册

> 适用范围：NVIDIA Thor、`sm_110a`、CUDA 13.0（ptxas V13.0.88、nvdisasm V13.0.85）
> 目的：完成 [`DAG方案可行性分析.md`](../DAG方案可行性分析.md) 中的阶段 0，即推导控制位码本与指令延迟表
> 全部步骤不需要执行 GPU 代码，只需 CUDA 工具链

## 本目录内容

| 文件 | 作用 |
|---|---|
| `extract_sass_model.py` | 从 nvdisasm 截获流中提取操作集与延迟表，替代上游失效的 `funnel.py` |
| `decode_ctrl.py` | 解码 cubin 中每条指令的调度控制位，并把等待归类为数据边、写重叠或屏障回收 |

## 步骤 0：环境自检

```bash
ptxas --version | tail -2
nvdisasm --version | tail -2
python3 --version
```

预期 CUDA 13.0。版本不同不影响流程，但导出的延迟表与版本绑定，须把版本号记入产物。

## 步骤 1：解码控制位

最短路径，不需要外部工具。

```bash
cd PTX_SASS_mapping/01_tcgen05
ptxas -arch=sm_110a -O3 -o /tmp/probe.cubin tcgen05.mma/thor_ptx90/generated/thor_tcgen05_mma_0000.ptx
python3 tools/decode_ctrl.py /tmp/probe.cubin --verify
```

输出每条指令的 `wait` 掩码、写屏障、读屏障、`yield`、`stall`，末尾给出等待分类统计。

关键读法：

| 列 | 含义 |
|---|---|
| `wait` | 发射前必须清零的记分牌集合 |
| 写屏障 | 本指令结果写回时置位的记分牌 |
| 读屏障 | 本指令读完源操作数时置位的记分牌，`STTM` 与 `UTCHMMA` 会用到 |
| `stall` | 发射后停顿周期数，固定延迟依赖靠它保证 |

`--verify` 把每个等待归为三类：

- `数据`：消费者引用了生产者写入的寄存器，即真正的依赖边。
- `写重叠`：两条指令写入集合相交，属于写后写顺序约束。
- `回收`：两者无寄存器关联。编译器为腾出屏障索引插入的等待。

**屏障回收边必须在做边包含比对时剔除**，否则自研生成器会被判为缺边。这是本工具最重要的一项输出。

若出现"等待了一个此前没有指令设置的屏障"，且同类异常成片出现，说明字段位置在该架构上有偏移，需回到步骤 3 复核。

导出结构化数据供后续比对：

```bash
python3 tools/decode_ctrl.py /tmp/probe.cubin --verify --json /tmp/probe_ctrl.json
```

## 步骤 2：导出官方延迟表

依赖上游工具 [DocumentSASS](https://github.com/0xD0GF00D/DocumentSASS/)，原理是 `LD_PRELOAD` 劫持 `nvdisasm` 的 `memcpy`，导出其内置的调度模型。

```bash
git clone --depth 1 https://github.com/0xD0GF00D/DocumentSASS.git
cd DocumentSASS
cc -fPIC -shared -o intercept.so intercept.c -ldl
```

上游的 `nvcc` 编译路径在部分系统上因 glibc 头文件冲突失败，直接用 `ptxas` 产物代替：

```bash
ptxas -arch=sm_110a -O3 -o probe.cubin <任意 tcgen05 PTX>
LD_PRELOAD=./intercept.so nvdisasm probe.cubin | strings -n 1 > intercept.txt
```

预期截获约 14 MB。上游的 `funnel.py` 在 CUDA 13.0 上不可用（它依赖的 `ARCHITECTURE` 标记已被移除，且 memcpy 流交错，无法按 src 指针整块重组），改用本目录脚本：

```bash
python3 <仓库路径>/tools/extract_sass_model.py intercept.txt -o sass_model
```

预期输出：约 940 行内容、52 个小节、86 条操作集定义、17 张延迟表。

产物中最要紧的两个文件：

| 文件 | 内容 |
|---|---|
| `sass_model/operation_sets.txt` | 全部操作集定义，含 `TCMMA_OPS`、`OP_TMA_TC`、`LDTM_STTM_OP`、`OP_SWS`、`UDP_subset` |
| `sass_model/tcgen05_summary.txt` | 只保留与 tcgen05 相关的操作集与延迟表行 |

## 步骤 3：阶段 0 的四项实验

以下四项做完，DAG 方案即可进入阶段 1。

### 3.1 屏障语义（最高优先级）

问题：记分牌是计数器还是标志位。若是计数器，则"所有异步指令共用一个屏障、所有消费者都等它"这一平凡正确策略成立；若是标志位，该策略失效，必须逐个分配。

做法：构造两条异步指令写入同一个屏障索引，在其后放一个消费者只等该屏障，观察是否两条都被等到。

```bash
# 构造 N 条 LDTM 写同一屏障的样本，逐一解码对比
python3 tools/decode_ctrl.py <cubin> --verify --json out.json
```

判据：若 ptxas 自身产生过"一个屏障被多条指令设置、后续单次等待"的形态，则为计数器。本目录已观察到 `LDCU` 与 `LDTM` 复用 `SB0` 的情形，倾向计数器，但未证实，必须复核。

### 3.2 字段位置复核

现用字段位置（word 1 内）：

| 字段 | 位 | 宽度 |
|---|---|---|
| reuse | [61:58] | 4 |
| wait 掩码 | [57:52] | 6 |
| 读屏障索引 | [51:49] | 3 |
| 写屏障索引 | [48:46] | 3 |
| yield | [45] | 1 |
| stall | [44:41] | 4 |

索引 7 表示不使用。该布局已在 `sm_110a` 上通过生产者与消费者配对自洽验证，例如三条 `LDCU` 分别置 `SB1`/`SB2`/`SB3`，其消费者 `UTCHMMA` 的等待掩码恰为 `0b001110`。

做法：用 `--verify` 跑遍全部已生成 case，统计异常数。

判据：异常应全部可解释为脚本的目的寄存器识别限制（例如寄存器对、谓词形态），而非成片的结构性错配。

### 3.3 延迟表对齐

`sass_model/tcgen05_summary.txt` 中的 `TABLE_TRUE(UGPR)` 给出：

```
OP_TMA_TC`{URa,...} / LDTM_STTM_OP`{...} / OP_SWS`{...}
= { UDP_subset`{URd,URd2} : 4 12 12 12 8 12 7 9 12 12 10 9 9 9 12
    R2UR_S2UR`{URd,URd2}  : 1  1  1  1 1  1 1 1  1  1  1 1 1 1  1 }
```

含义：tcgen05 指令读取某个 UR 时，若该 UR 由 `UDP_subset` 成员产生，固定延迟取向量中对应位置的值；若由 `R2UR_S2UR`（含 `LDCU`）产生则为 1 周期，其余部分走记分牌。

未解决项：向量中每个数值对应 `UDP_subset` 的哪个成员。`UDP_subset` 是差集：

```
UDP_subset = UDP_OPS - R2UR_S2UR - OP_R2UR_COUPLED
             - ULDC_VOTEU_UMOV_ULEPC - OP_TMA_TC
             - OP_UGETNEXTWORKID - LDTM_STTM_OP - __HIR0X1F4 - OP_SWS
```

做法：从 `operation_sets.txt` 解出各集合成员并求差集，按定义顺序与向量逐位对齐；再用 `decode_ctrl.py` 观察到的实际 `stall` 值抽样验证。

判据：抽样点的实测 `stall` 应不小于表中对应值。

### 3.4 屏障回收策略

问题：编译器何时插入回收等待、按什么顺序复用索引。

做法：用步骤 1 的 `--verify` 统计不同异步深度下回收边的数量与位置。

判据：能写出一条可复现的规则，例如"索引用满前不回收"或"在最近的控制流汇合点回收"。该规则决定自研生成器能否在长序列上不耗尽索引。

## 步骤 4：产物归档

每次运行都记录以下信息，否则结果不可比：

```bash
ptxas --version | tail -1
nvdisasm --version | tail -1
sha256sum intercept.txt
```

延迟表与工具链版本强绑定。换 CUDA 版本必须整套重跑，不能沿用旧产物。

## 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `nvcc` 报 `rsqrt` 声明冲突 | CUDA 头文件与系统 glibc 不兼容 | 不用 `nvcc`，改用 `ptxas` 生成 cubin |
| 截获文件只有几 KB | cubin 不存在或 `nvdisasm` 未真正反汇编 | 确认 cubin 有效，先单独跑一次 `nvdisasm` |
| 提取后内容行为 0 | 截获失败或 `intercept.so` 未生效 | 确认 `LD_PRELOAD` 路径是相对当前目录的 `./intercept.so` |
| `decode_ctrl.py` 解析到 0 条指令 | 输入不是 cubin，或 nvdisasm 不支持该架构 | 用 `nvdisasm -hex -c` 手工确认输出格式 |
| 回收边数量异常多 | 助记符含小写修饰符导致目的寄存器识别失败 | 检查 `DEST_RE` 是否覆盖该助记符形态 |

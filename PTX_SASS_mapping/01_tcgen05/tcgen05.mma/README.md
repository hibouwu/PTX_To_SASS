# tcgen05.mma 测试用例

本目录按《实验设计_详细规范》的对象层级和维度划分，生成 NVIDIA Thor 对应的 PTX ISA 9.0 `tcgen05.mma` 静态编译降级（lowering）用例。

## 产物

[`thor_ptx90/`](thor_ptx90/) 目录：面向 NVIDIA Thor、PTX ISA 9.0、编译目标 `sm_110a` 的受约束穷举生成器。

- 语法集：1,152 个源码实现，896 个 semantic form
- 扩展集：9,216 个源码实现，7,168 个 logical design
- 协议层：34 个 `CTX.protocol` 和 8 个完整效应切片（effect slice）case
- 全部编译 O0/O1/O2/O3 四档

执行：

```bash
cd thor_ptx90
./check_all.sh
```

## 维度裁决

### 先区分限定符（qualifier）的语义轴

不能建立一个包含 `.rn`/`.sat`/`.global`/`.gpu`/`.ca` 的通用笛卡尔积再套到每条 PTX 指令上。名称相似的限定符也可能属于不同语义轴：

| 语义轴 | 常见限定符 | 操作行为 | 实验归属 | 对 `tcgen05.mma` 本体 |
|---|---|---|---|---|
| 舍入模式 | `.rn`、`.rz`、`.rm`、`.rp` | 最近偶数、向零、向负无穷、向正无穷舍入 | 目标支持时属于 `SF.rounding` | 语法不支持，不得拼到操作码上 |
| 数值后处理 | `.sat`、`.ftz`、`.relu` 等 | 饱和、次正规数清零或指令专属后处理 | 目标支持时属于 `SF.behavior` | `.sat`/`.ftz` 语法不支持 |
| 状态空间 | `.global`、`.shared{::cta,::cluster}`、`.local`、`.param` | 指定地址属于哪个存储空间 | 内存目标属于 `SF.state_space`；邻接生产者属于其 `semantic_form_id` | MMA 操作码没有此轴；A/B 描述符描述 SMEM，D/A address 可指 TMEM |
| 内存序 | `.weak`、`.relaxed`、`.acquire`、`.release`、`.acq_rel`、`.sc` | 定义排序与同步语义 | 内存/同步目标的 `SF.memory_order` | 语法不支持 |
| 作用域 | `.cta`、`.cluster`、`.gpu`、`.sys` | 指定哪些线程可直接观察同步效应 | 内存/同步目标的 `SF.scope` | 语法不支持；不要与 `.cta_group` 混同 |
| 缓存策略 | `.ca`、`.cg`、`.cs`、`.lu`、`.cv`、eviction/prefetch hint | 控制或提示缓存层级、流式性、逐出和预取 | 内存目标的 `SF.cache_policy` | MMA 操作码没有此轴 |
| 执行/参与约束 | `.sync`、`.aligned`、`.uni`、`.cta_group::N` | 规定参与集合、收敛/对齐契约或执行组 | 目标支持时属于 `SF.execution_contract` | 只直接支持 `.cta_group::1/2`；MMA 是单线程发射 |
| 操作模式 | `.kind::*`、`.sp`、`.ws`、`.block_scale`、`.collector::*`、`.ashift` | 选择数据路径、稀疏/WS 模式、分块缩放、collector 生命周期或 A 行移位 | `SF.*` | 直接适用，但有严格合法组合约束 |

`.shared::cta`/`.shared::cluster` 中前半部分是状态空间、后半部分是 shared window 子空间。它与同步作用域 `.cta`/`.cluster`/`.gpu`/`.sys` 不是同一字段。例如 `mbarrier.arrive.release.cluster.shared::cta.b64` 同时具有 memory order、scope 和 state space，三者必须分别记录。类似地，`.cta_group::2` 表示 MMA 涉及执行 CTA 与 peer CTA 的张量内存（Tensor Memory，TMEM），不表示 `.cluster` memory scope。

缓存操作符对普通 `ld`/`st` 是性能提示，不改变程序的 memory consistency。`.ca`/`.cg` 与 `.acquire`/`.release` 必须拆成两个轴。即使两者都改变 SASS，也不能合并成"内存模式"单因素。

### `tcgen05.mma` 的合法操作模式分类

本套件固定 PTX ISA 9.0、编译目标 `sm_110a`。直接参与 `tcgen05.mma` 语法和操作行为的字段按下表登记。"不出现限定符"也应记录其规范默认行为，不能写成含义不明的 `DEFAULT`：

| 分类 | PTX 9.0 形态/取值 | 关键约束 | 字段归属 |
|---|---|---|---|
| 指令变体 | `mma`、`mma.sp`、`mma.ws`、`mma.ws.sp` | `.sp` 增加稀疏元数据；`.ws` 只有 `.cta_group::1` | `SF.mma_variant` |
| CTA group | `.cta_group::1/2` | 同一 kernel 中所有 tcgen05 指令必须取相同值；`.ws` 仅 group 1 | `SF.cta_group` |
| MMA kind | `.kind::f16`、`tf32`、`f8f6f4`、`mxf8f6f4`、`mxf4`、`mxf4nvf4`、`i8` | kind 只给出类型家族；精确 A/B/D 类型、M/N/K、主方向等由 `idesc` 固定 | `SF.kind` + `SF.idesc.*` |
| A 来源形态 | `a-desc` 或 `[a-tmem]` | 不同语法形态；描述符位型/来源与 TMEM 地址来源另行记录 | `SF.a_operand_form` |
| 分块缩放 | `.block_scale` + `.scale_vec::1X/2X/4X` | 仅 `mxf8f6f4`/`mxf4`/`mxf4nvf4`；kind、K 与 scale-vector 存在合法组合 | `SF.block_scale.*` |
| collector | `.collector::a::{fill,use,lastuse,discard}` | `use`/`lastuse` 依赖先前合法 fill；省略表示 `a::discard` | `SF.collector_usage` + `CTX.protocol.*` |
| A 行移位 | `.ashift` | 仅 A 来自 TMEM 且 M=128/256；不能与 collector `fill`/`use` 非法组合 | `SF.ashift` |
| D 累加控制 | `enable-input-d` 谓词操作数 | false 为 `D=A*B`，true 为 `D=A*B+D` | 操作数是 `SF` 角色；值/已知性为 `CTX.value.*` |
| D 缩放 | 可选立即数 `scale-input-d`，范围 0–15 | 通用文法存在，但 CUDA 13.0 `ptxas` 在 `sm_110a` 上拒绝；仅作为阴性 capability probe | `SF.scale_input_d` |
| 输出 lane 掩码 | 4/8 个 32-bit `disable-output-lane` 操作数 | 个数由 CTA group 决定 | 形状为 `SF`；位型为 `CTX.value.*` |

特别区分三种"看起来都像指令修饰"的信息：

1. 操作码限定符（例如 `.kind::tf32`），直接进入 `semantic_form_id`。
2. `idesc`/SMEM 描述符中的编码字段（例如 shape、精确 dtype、major 和 swizzle），同样定义语义形态，但不以操作码限定符出现。
3. 谓词、mask、描述符和 TMEM 地址的具体生产方式与运行时值，属于 `CTX.*` 或 `RUN.*`，不能因为它们影响行为就并入限定符轴。

`tcgen05.commit...shared::cluster.b64` 中的 `.shared::cluster` 属于完成协议节点的 state space，不是 `tcgen05.mma` 的 state-space 限定符。

规范依据为 [PTX ISA 9.0](https://docs.nvidia.com/cuda/archive/13.0.1/parallel-thread-execution/index.html) 中的舍入修饰符、缓存操作符、内存一致性模型以及 `tcgen05.mma`/`tcgen05.commit` 章节。每个生成 case 的机器可读坐标保存在 `thor_ptx90/generated/manifest.jsonl`，字段归属遵循本仓库的 [`实验设计_详细规范.md`](../../实验设计_详细规范.md)。

基于上述裁决，当前生成用例中的 `kind`、`cta_group`、dense/sparse、A 操作数是 SMEM 描述符还是 TMEM 地址、block scale、collector 和 `ashift` 都会改变指令语义形态，归入 `SF.*`，不解释为同一 seed 内的上下文效应。

同一语义形态内操纵的 `CTX.*` 包括：

- `enable-input-d` 的已知性与真值、disable-output-lane mask 位型。
- A/B 描述符的定义身份、直接参数生产者或等价派生链。
- 目标 PTX guard、直线/分支控制流图和 lane 0 issuer 构造。
- 无完成节点或 `commit.mbarrier::arrive::one`。

## 覆盖口径

当前是合法限定符表面形式的受约束穷举，并提供与 8 个静态上下文配置文件交叉的扩展集。协议层另外覆盖 allocation、fence、commit/mbarrier、LD/ST wait 和完整生命周期效应切片。它不是描述符位字段或运行时状态的无约束笛卡尔积。

尚未覆盖：

- 所有合法描述符 shape/type/swizzle 组合及真实描述符数值。
- 跨线程发射/完成同步、CTA pair 的真实 cluster 生命周期。
- alloc/dealloc、TMEM load/store 和运行时数值正确性。

生成的 raw descriptor/TMEM 地址用例只用于静态汇编与 PTX→SASS 归属，不得启动执行，也不能据此标记 `SEMANTIC_PASS`。

## 操作检查

独立源码解析器重新读取 manifest 和生成的 PTX，检查非零且符合 summary 的 source/case 数、kernel/CASE marker、逐条 occurrence、精确目标指令、guard、lane 0 issuer、producer chain 和 commit。编译成功还必须产生非空 cubin。

效应切片另用 `nvdisasm` 检查关键 SASS 路径是否保留。核心 MMA 分片编译后按 `.text.<kernel>` 切分 `nvdisasm` 输出，并按源码顺序把每个 `tcgen05.mma` occurrence 与对应的 `UTCHMMA`/`UTCIMMA`/`UTCQMMA` 系列指令配对。原始 SASS 保存在工作目录的 `sass/raw/`，逐 occurrence 结果保存在 `sass/sass_attribution.jsonl`。该归属只覆盖 MMA 核心指令。融合、移动、共享节点、操作数准备以及完整效应图仍需在后续映射分析中记为 `OBS.*`。

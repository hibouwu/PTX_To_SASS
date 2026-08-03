# NVIDIA Thor / PTX ISA 9.0 tcgen05.mma 生成矩阵

本目录生成面向 NVIDIA Thor（计算能力 compute capability 11.0）的 `.version 9.0`、`.target sm_110a` 静态汇编用例。

## 已验证结果

验证环境为 CUDA 13.0 `ptxas` V13.0.88，二进制 SHA-256 为 `daba837a68265cae38c832d13399b61dab811891de9b8914defddef143b849f2`。

| 集合 | 源码实现 | semantic form | logical design | occurrence | O0/O1/O2/O3 汇编 |
|---|---|---|---|---|---|
| `syntax` | 1,152 | 896 | 896 | 1,648 | 72/72 通过 |
| `expanded` | 9,216 | 896 | 7,168 | 13,184 | 576/576 通过 |
| `CTX.protocol` | 34 | — | 34 | — | 136/136 通过 |
| `effect_slice` | 8 | — | 8 | — | 32/32 通过 |
| 预期拒绝探针 | 3 | — | 3 | 3 | 3/3 通过 |

仓库保留默认生成结果。各层编译摘要和阴性探针诊断保存在 [`validation/`](validation/)。

除协议层 168/168 次汇编通过外，检查器还对 8 个效应切片的四个优化版本执行 32/32 次 `nvdisasm` 操作检查。每个版本必须实际保留 `UTCHMMA`、`UTCBAR`、mbarrier phase wait、`LDTM` 和 TMEM dealloc。带 ST 的切片还必须保留 `STTM`，避免只汇编成功但关键路径被优化删除。

这里的 1,152/9,216 是源码实现数，不是唯一 semantic-form 数。隐式 collector discard 与显式 discard，以及无需 `idesc.K` 就能证明等价的 block-scale 拼写，会保留为不同 `source_variant`，但共享同一 `semantic_form_id`。对于依赖 K 值才等价的 `.block16`/`.block32` 别名，生成器不会在 `idesc` 未冻结时强行合并。上下文身份不包含 profile 名称，只由完整规范化赋值计算。

## 生成范围

默认 `syntax` 模式对以下受约束语法空间做穷举：

- `mma`、`mma.sp`、`mma.ws`、`mma.ws.sp`
- `.cta_group::1/2`（WS 固定 group 1）
- `f16`/`tf32`/`f8f6f4`/`i8` 以及带分块缩放的 `mxf8f6f4`/`mxf4`/`mxf4nvf4`
- A 使用 SMEM 描述符或 TMEM 地址
- `.scale_vec::1X/2X/4X`、`.block16/.block32` 的合法 kind 组合和允许的缺省拼写
- A collector 和 WS 的 B0–B3 collector：隐式/显式 discard、fill、`fill→use`、`fill→lastuse`
- 普通 MMA 中 A 来源为 TMEM 时的 `.ashift` 合法构造
- WS zero-column-mask 描述符的缺省/存在

PTX ISA 9.0 的通用 `tcgen05.mma` 文法还列出 `scale-input-d`，但 CUDA 13.0 `ptxas` 对 `.target sm_110a` 明确拒绝这个 side operand。因此它不进入 Thor 正向用例分母，只进入预期拒绝的 capability probes。`.ashift` 仅出现在普通 TMEM-A 形态中，不能与分块缩放或 SMEM-descriptor A 形态做无约束组合。

`expanded` 模式再与 8 个静态上下文配置文件交叉，包括 enable 常量、全一 mask、正/负 PTX guard、lane 0 issuer、派生 producer 和 commit completion。

## 使用

一键重新生成并编译以下四层的 O0/O1/O2/O3 四个版本，执行 expanded 上下文配对差分和阴性探针：

- `syntax`：合法限定符/操作数表面形式
- `expanded`：表面形式与 8 个静态上下文配置文件的交叉
- `CTX.protocol`：allocation、fence、commit/mbarrier、LD/ST wait
- `effect_slice`：alloc→可选 ST/wait→MMA→commit/mbarrier wait→LD/wait→dealloc 的完整序列

```bash
./check_all.sh
```

默认使用 4 个并行任务，完整运行结果写入本目录的 `results/`。其中包括 cubin、SASS、活跃寄存器反汇编、逐配对 JSONL 和完整日志。`results/.gitignore` 会阻止 `.cubin`、`.sass` 和体积较大的逐记录 `.jsonl` 文件进入 Git。

最终适合直接阅读的中文报告发布到 `Docs/tcgen05_mma_上下文差分报告.md`。按单个修饰符或语义维度查规则时，从 [`Docs/mapping_rules/README.md`](Docs/mapping_rules/README.md) 进入。需要跨维度解释和完整函数级 PTX/SASS 时，阅读 [`Docs/tcgen05_mma_PTX到SASS映射规则报告.md`](Docs/tcgen05_mma_PTX到SASS映射规则报告.md)。

可选参数依次是并行任务数和工作目录。例如 `./check_all.sh 8` 仍写入默认 `results/`，只有显式执行 `./check_all.sh 8 /path/to/work` 时才改用其他目录。无论工作目录在哪里，最终 Markdown 报告都发布到 `Docs/`。

所有会被脚本清理的目录都带 `.tcgen05-suite-owner.json` ownership marker。脚本只重建新目录或 owner 匹配的目录，并拒绝 `/`、过短绝对路径、当前目录、仓库目录/祖先以及无 marker 的已有目录。

协议层由 [`generate_protocol_layers.py`](generate_protocol_layers.py) 生成，默认源码和清单位于 [`protocol_generated/`](protocol_generated/)。[`check_protocol_layers.py`](check_protocol_layers.py) 负责四优化级汇编。`CTX.protocol` 的 allocation case 穷举 `.cta_group::1/2`、generic/`.shared::cta` 和合法 `nCols={32,64,128,256,512}`。commit 覆盖 generic、`.shared::cluster` 与 `.multicast::cluster`，mbarrier 覆盖 CTA/cluster scope 以及 relaxed 和 release/acquire 配对。

生成仓库内的默认语法矩阵：

```bash
python3 generate_cases.py
```

只检查一个集合；不指定 `--optimizations` 时同样编译 O0/O1/O2/O3：

```bash
python3 check_cases.py --mode syntax --jobs 4
```

生成更大的上下文扩展集：

```bash
python3 generate_cases.py --mode expanded --output /tmp/thor-expanded
python3 check_cases.py --mode expanded --jobs 4
```

如果 cubin 已经存在，也可以只重新提取和归属 SASS：

```bash
python3 extract_core_sass.py \
    --source-dir results/expanded/sources \
    --cubin-dir results/expanded/cubins \
    --output-dir results/expanded/sass
```

对 expanded 结果进行基线/上下文配对差分：

```bash
python3 compare_context_lowering.py \
    --source-dir results/expanded/sources \
    --sass-dir results/expanded/sass \
    --output-dir results/context-comparison \
    --report-output Docs/tcgen05_mma_上下文差分报告.md
```

差分目录包含逐配对的 `context_differences.jsonl`、汇总表 `context_summary.csv` 和中文报告 `context_report.md`。默认以 `runtime_zero` 为基线，按 `semantic_form_id` + `source_variant_id` + `optimization` 严格配对。报告除了指令选择和完整 kernel 序列，还单独回答：

- 核心 MMA 的具体寄存器布局是否改变
- 变化是否只是编号重排，R/UR/P/UP 类别和寄存器复用关系是否改变
- 核心指令处和整个 kernel 峰值的 GPR/PRED/UGPR/UPRED 活跃数是否改变
- kernel 引用的寄存器集合以及 `LDL*`/`STL*` 本地内存指令是否改变

活跃数取自 `nvdisasm --life-range-mode count`。`LDL*`/`STL*` 只作为潜在溢出（spill）指标，不能脱离编译资源信息直接解释为寄存器溢出。

检查 Thor 明确不支持的限定符 capability probes：

```bash
python3 check_negative_probes.py
```

生成器以 64 个 kernel 为一个 PTX 分片，避免把"文件数"误当成 case 数。`manifest.jsonl` 每行是一条源码实现，并将以下身份分开记录和哈希：

- `semantic_form`：规范化后的操作语义，不含 guard、producer 等 `CTX`
- `static_context_assignment`：完整展开的 enable/mask/guard/issuer/producer/completion 赋值
- `source_variant`：implicit/explicit collector、scale-vector alias 等实际拼写

生成器连续运行的清单、summary、首尾分片 SHA-256 一致，输出顺序和 case identity 是确定的。

生成后会由独立解析器重新读取清单和 PTX，核对非零 source/case 数、summary 数量、kernel/CASE marker、逐条 target occurrence、精确目标指令文本、guard、lane-0 issuer、producer chain 和 commit。编译检查还要求每个成功任务产生非空 cubin，随后调用 `nvdisasm`，按 `.text.<kernel>` 切分 SASS，并按源码顺序将每个目标 occurrence 配对到 `UTCHMMA`/`UTCIMMA`/`UTCQMMA` 系列核心指令。

## 验证边界

成功 `ptxas -arch=sm_110a` 仅证明 CUDA 13 工具链接受该 PTX 语法并能为 Thor 生成 cubin。所有描述符、TMEM 地址和 mbarrier 地址仍是原始参数。没有冻结合法的描述符位型、分配 TMEM 或在 Thor 上执行。因此这些用例是 `STATIC_ASSEMBLY_ONLY`，不能据此升级为 `SEMANTIC_PASS`。

效应切片保持 alloc/dealloc/relinquish 的 warp collective 源码形态，并只将 MMA、commit 和 mbarrier 管理限制为 issuer thread。但 `.cta_group::2` 仍需要 Thor 实机以 peer CTA/cluster launch 验证。静态汇编不能证明双 CTA 参与契约成立。

后续实机阶段必须另外加入：

- 按 kind/shape/type/major/swizzle 生成的合法 `idesc` 和 SMEM 描述符
- Thor 实机有效的 descriptor/TMEM 分配与跨线程 canonical lifecycle
- 数值 oracle、非法组合阴性对照和 Compute Sanitizer
- Thor 上的 driver/runtime 身份及逐 workload 的实际路径证据

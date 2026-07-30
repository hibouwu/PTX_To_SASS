# PTX 指令心智模型：从规范视角"读懂"一条 PTX 指令

> 本文档目标：**建立一套通用的、可机械执行的"读指令流程"**。让你拿到任何一条 PTX 指令（哪怕是从没见过的 opcode），都能快速理解它在做什么、查手册时该看哪些维度、ptxas 可能怎么 lowering。

---

## 1 一条 PTX 指令的通用解剖

任意一条 PTX 语句都可以套进下面这个"模板"：

```
[pred@]  opcode [qualifier...]  [dst], src1, src2, src3  ;
```

逐段拆开，一共 6 个"槽位"（并非每条都齐备）：

| 槽位 | 形式 | 作用 | 例子 |
|---|---|---|---|
| **Guard（谓词）** | `@p1` / `@!p1` | 条件执行：若谓词为真才执行 | `@p1 add.f32 ...` |
| **Opcode（操作码）** | `ld` / `add` / `wgmma` | 核心语义："做什么" | `add` |
| **Qualifiers（限定符串）** | `.global.ca.f32` | 参数化语义："怎么做、对什么做、在哪做" | 见 §2 |
| **Destination（目的）** | `%rd1` / `{a,b}` | 写回结果的位置 | `%f1` |
| **Sources（操作数）** | 寄存器 / 立即数 / 标签 | 输入数据 | `%r2, 4.0` |
| **Side qualifiers（尾部修饰）** | `.sync`、对齐值、标签列表等 | 某些指令独有的后置修饰 | `bar.sync` 的目标计数 |

**核心心智模型 #1**：PTX 的指令表达力 = **少量 opcode × 多维 qualifier 矩阵 × guard × 立即数**。看一条指令 = 把这四个维度逐个固定下来。

---

## 2 六个"心智切面"：一条指令的六个问题

看到一条指令，按顺序问自己这六个问题，每个问题对应一个切面：

### ① 这条指令**在做什么操作**？→ Opcode 族

PTX 有约 200 条 opcode，但按语义只分为约 15 个族：

| 族 | 代表 opcode | 典型 SASS 对应 |
|---|---|---|
| 算术（整） | `add/sub/mul/mad/abs/neg` | IADD3, IMAD, IMNMX |
| 算术（浮） | `add/mul/fma/mad/abs/neg` | FFMA, FMNMX, DMNMX |
| 特殊函数 | `rcp/sqrt/rsqrt/sin/ex2/lg2` | MUFU.RCP 系列 |
| 比较 | `setp/set` | FSETP, ISETP, ISET |
| 逻辑/移位 | `and/or/xor/shl/shr` | LOP3.LUT |
| 数据移动 | `mov/cvt` | MOV, F2I, I2F |
| 内存 | `ld/st/atom/ldmatrix` | LDG, STG, ATOM, LDSM |
| 视频 SIMD | `vadd/vmin/vmax/vabsdiff/vmul` | VMNMX, VSET, VABSDIFF4 |
| WGMMA/TC | `wgmma.mma_async / tcgen05.mma` | WGMMA, HMMA |
| 控制流 | `bra/call/ret/exit` | BRA, CALL, RET, EXIT |
| 同步/通信 | `bar/membar/atom/activemask` | BAR.SYNC, MEMBAR |
| Warp Shuffle | `shfl.sync` | SHFL.BFLY/.UP/.DOWN/.IDX |
| 寄存器重命名 | `prmt/lop3/bfe/bfi/bfind` | PRMT, BFE, BFI |
| 系统 | `red/vote/nanoid` | RED, VOTE |

**查规范的第一原则**：先看族，确定大致章节；再看该 opcode 的具体条目。

### ② 数据**在哪**？→ 空间（State Space）qualifier

```
ld.global.f32 ...    // global 空间
ld.shared.f32 ...    // shared 空间
ld.local.u32  ...    // local 空间
ld.const.f32  ...    // const 空间
ld.param.u64  ...    // param 空间
ld.f32 ...           // 无空间限定 = generic（运行时判断）
```

**这一维是 lowering 最重要的切分**：
- `.global/.const` → `LDG` / `LDC`
- `.shared` → `LDS`
- `.local` → `LDL`（实际走 L1 但地址映射到 global）
- `.param` → 常量 bank 槽位 / 寄存器槽位（取决于 kernel 还是设备函数）
- 无空间 → 运行时根据地址高位选择（`LDC` vs `LDG`）

### ③ 对**什么类型**的数据做？→ 类型 qualifier

`.b8/b16/b32/b64`、`.u8/u16/u32/u64`、`.s8/s16/s32/s64`、`.f16/f32/f64`、`.f16x2`、`.pred`。

**强类型**是 PTX 区别于传统汇编的最重要特征：
- 类型决定选哪条 SASS（`add.s32` 和 `add.f32` 是两条完全不同的 SASS）；
- 类型不匹配（`add.f32 %r1, %r2, %r3` 但 r2/r3 是 .u64）ptxas 直接报错；
- 类型 + 空间 共同约束宽度合法性（例如 `.shared` 支持 `b8`，`.param` 一般只支持 b32/b64）。

### ④ 操作**具体怎么做**？→ 行为 qualifier

| 修饰 | 适用指令 | 含义 |
|---|---|---|
| `.rn / .rz / .ru / .rd` | 浮点算术 | round nearest / zero / up / down |
| `.ftz` | 单精度浮点 | 非正规数 flush to zero（更快） |
| `.sat` | 算术 | 结果饱和到 [0,1]（整数到类型范围） |
| `.wide` | `mul/mad` | 32×32→64 |
| `.hi / .lo` | 宽乘除 | 取高位/低位 |
| `.full` | `div` | 完整精度（vs `.approx`） |
| `.approx` | `div/rcp/sqrt/rsqrt/ex2/lg2/sin/cos` | 用硬件 MUFU 快速近似 |
| `.v2 / .v4` | 数据移动 | 向量化搬运 |

**关键心智 #2**：行为 qualifier 大多是 **正交** 的——舍入、饱和、宽度互不影响，可任意组合。

### ⑤ **谁**来执行？→ 收敛性 / 同步 qualifier

| qualifier | 含义 |
|---|---|
| `.sync` | warp 级同步操作（`shfl.sync`、`bar.sync`） |
| `.aligned` | 要求 warp 内所有线程都到达（`bar.sync`） |
| `.uni` | 调用者声明所有线程走同一分支（`call.uni`） |
| `.relaxed / .acquire / .release / .weak` | 内存序修饰 |
| `.cta / .cluster / .gpu / .sys` | 同步/内存可见性范围 |

**这一维与"正确性"强绑定**：去掉 `.sync` 的 `shfl` 在新架构上直接非法；`.weak` 内存序允许硬件合并访存。

### ⑥ **结果**在哪？→ 目的操作数形式

- 单寄存器 `%r1` → 普通写入
- 寄存器元组 `{%r1,%r2,%r3,%r4}` → 向量化结果、warp 级归约
- 谓词寄存器 `p1`（不带 `%`） → 写入条件码
- 特殊寄存器如 `%ftz`、`%rm` → 写系统状态

---

## 3 实例演练：逐段解读

### 例 1：`@p1 ld.global.ca.v4.f32 {%f1,%f2,%f3,%f4}, [%rd1];`

| 槽位 | 内容 | 含义 |
|---|---|---|
| guard | `@p1` | 仅当 p1 为真时执行 |
| opcode | `ld` | 读 |
| 空间 | `.global` | 从 global 显存读 |
| cache | `.ca` | cache at all levels |
| 向量 | `.v4` | 一次搬 4 个 |
| 类型 | `.f32` | 每个元素 32 位浮点 |
| dst | `{%f1..%f4}` | 结果写 4 个浮点寄存器 |
| src | `[%rd1]` | 地址来自 %rd1 |

→ SASS 上对应一条 128 位 LDG.128。

### 例 2：`add.rn.ftz.f32 %f1, %f2, %f3;`

| 槽位 | 内容 |
|---|---|
| opcode | `add` |
| 舍入 | `.rn`（round to nearest） |
| ftz | `.ftz`（flush-to-zero） |
| 类型 | `.f32` |

→ SASS: FADD.FTZ 或 FFMA（被优化为 FMA）。

### 例 3：`wgmma.mma_async.sync.aligned.m64n256k16.f32.f16.f16`

| 槽位 | 内容 |
|---|---|
| opcode | `wgmma.mma_async`（Tensor Core WGMMA） |
| 同步 | `.sync.aligned`（必须 warp 内所有线程都到达） |
| 形状 | `.m64n256k16`（矩阵维度） |
| 类型链 | `.f32.f16.f16`（D=f32，A=f16，B=f16） |

→ SASS: WGMMA.M64N256K16.F32.F16.F16

---

## 4 看规范的"四步法"

遇到一条不熟悉的 PTX 指令，按下面四步查手册：

**Step 1. 按 opcode 定位章节。** PTX ISA 第 9 章按指令族分组（§9.7.1 整数 / §9.7.2 浮点 / §9.7.3 比较 ... §9.7.15 视频 SIMD ...），先找到族，再定位具体条目。

**Step 2. 看该条目的"qualifier 矩阵"。** 手册对每条指令都列了一张表，行是空间 / 类型 / 舍入等维度，列是合法性。这张表 = **你能写的所有合法 qualifier 组合**。

**Step 3. 看 Action 与 Syntax。** Action 描述语义（如 "dst = src1 + src2"），Syntax 给出模板（`opcode.qual dst, src1, src2;`）。

**Step 4. 看 Examples / Target ISA Notes。** 例子给出真实用法，"Target ISA Notes"告诉你哪些架构版本支持哪些 qualifier 组合——这一步对自研 ptxas **尤其关键**，因为它直接决定哪些组合可以 emit、哪些要报"unsupported"。

---

## 5 与 SASS 的关系：lowering 视角的"等价翻译"

PTX 指令 ≠ SASS 指令。ptxas 做的本质工作就是：

```
PTX 指令 + 所有 qualifier → 选择一条 SASS + 填充 modifier 编码位
```

对应关系大致是：

| PTX 维度 | SASS 对应物 |
|---|---|
| opcode | SASS 主 opcode（LDG, IADD3, FFMA ...） |
| 空间 | SASS 指令类别（LDG vs LDS vs LDL vs LDC） |
| 类型 | SASS 的 type 编码字段（32/64/...） |
| 舍入 / 饱和 / ftz | SASS 的 modifier bits |
| 同步 / 内存序 | SASS 的 memory descriptor 字段 / barrier 插入 |
| cache 提示 | SASS 的 cache policy 字段（可选映射） |
| guard `@p` | SASS 的 predication 字段（`.P1`） |

**所以心智模型 #3**：你在 PTX 上看到的每个 qualifier，在 SASS 那边**要么对应一个编码位，要么对应一条指令选择**，要么（极少数情况）被丢弃。

---

## 6 常见误区清单

1. ❌ "PTX opcode 多 = SASS opcode 多"
   → PTX 的 qualifier 是乘法关系，SASS 的 opcode 只有几十个，靠 modifier 位表达丰富语义。

2. ❌ "每条 PTX 指令对应一条 SASS"
   → 复杂指令（如 `.approx div`、`atom.global.max`）会被展开为多条 SASS。

3. ❌ "qualifier 顺序随意"
   → PTX 文法严格规定 qualifier 顺序，`ld.global.f32` 合法但 `ld.f32.global` 非法。

4. ❌ "generic 空间等于 global"
   → generic 是运行时判断，可能落 global / shared / const / local（通过 `cvta` 系列映射）。

5. ❌ "`.param` 是内存空间"
   → 它只是"参数传递"的虚拟抽象，lowering 到 constant bank（kernel）或寄存器（设备函数）。

---

## 7 一句话总结

> **PTX 指令 = 操作码 × 空间 × 类型 × 行为 × 同步 × 目的槽位，每个维度独立正交。**
> 看一条指令 = 把这六个维度逐个固定下来；
> 查手册 = 按 opcode 定位 + 看该 opcode 的 qualifier 矩阵 + 看架构支持；
> 写 ptxas = 把这六个维度映射到 SASS 的 opcode 选择和编码位填充。

把这张图刻在脑子里，PTX 第 9 章的两百多条指令就不再是清单，而是一个**六维张量**——你只是在不同的"切片"上取不同的值。

---

> **相关阅读**：[SASS_指令心智模型.md](file:///root/cuda/cuda_ori_notes/SASS_指令心智模型.md) —— PTX 的"物理层"对照：PTX 回答"做什么"，SASS 回答"硬件上怎么做"。

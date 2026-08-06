# PTX → NVPTX LLVM IR 转换工具

基于 [ZLUDA](https://github.com/vosen/ZLUDA) 的 `ptx` crate，修改目标后端为 **NVPTX**，将任意 PTX 文件直接转成可被 LLVM NVPTX 后端处理的 `.ll` 文件。

---

## 环境准备

首次运行需要编译 LLVM（AMDGPU target，约 30 分钟，之后增量编译很快）：

```bash
cd PTX_IR/ZLUDA

# 1. 构建 LLVM（仅首次，已有 target/debug/build/llvm_zluda-*/out/build 则跳过）
#    如果遇到 "build.ninja still dirty" 错误，在 CMakeCache.txt 所在目录执行：
#    cmake -DCMAKE_SUPPRESS_REGENERATION=ON <build_dir>
#    touch <build_dir>/build.ninja

# 2. 编译 dump_ir 工具
cargo build -p ptx --example dump_ir
```

编译成功后二进制在：
```
target/debug/examples/dump_ir
```

---

## 使用方法

```bash
DUMP=PTX_IR/ZLUDA/target/debug/examples/dump_ir

# 基本用法：PTX → NVPTX IR 打印到 stdout
$DUMP path/to/kernel.ptx

# 保存到文件（stderr 是 pass 进度，2>/dev/null 可静默）
$DUMP path/to/kernel.ptx 2>/dev/null > output.ll
```

### 示例

```bash
cd /home/jianyeshi/Note/PTX_To_SASS
DUMP=PTX_IR/ZLUDA/target/debug/examples/dump_ir

# vecadd（sm_80）
$DUMP PTX_IR/tests/vecadd.ptx 2>/dev/null > PTX_IR/tests/vecadd_nvptx.ll

# layernorm（sm_110，含 rsqrt.approx.f32）
$DUMP Attention/layernorm.ptx 2>/dev/null > PTX_IR/tests/layernorm_nvptx.ll

# softmax（sm_110，含 ex2.approx.f32 × 8）
$DUMP Attention/softmax_mt.ptx 2>/dev/null > PTX_IR/tests/softmax_mt_nvptx.ll
```

---

## 输出 IR 说明

生成的 `.ll` 是标准 NVPTX LLVM IR，主要特征：

| 元素 | 示例 | 含义 |
|---|---|---|
| 调用约定 | `ptx_kernel void @vecadd(...)` | NVIDIA GPU kernel（CC 71） |
| 参数空间 | `ptr addrspace(101) byref(i64)` | PTX `.param` 状态空间 |
| 全局内存 | `ptr addrspace(1)` | global memory |
| 寄存器/局部 | `alloca ... addrspace(5)` | private/scratch |
| 共享内存 | `addrspace(3)` | shared memory |
| 目标 CPU | `"target-cpu"="sm_110"` | 来自 PTX `.target sm_xxx` |
| 线程 ID | `@llvm.nvvm.read.ptx.sreg.tid.x()` | `%tid.x` |
| Block ID | `@llvm.nvvm.read.ptx.sreg.ctaid.x()` | `%ctaid.x` |

### PTX 指令 → NVVM intrinsic 对照

| PTX 指令 | LLVM NVVM intrinsic |
|---|---|
| `rsqrt.approx.f32` | `@llvm.nvvm.rsqrt.approx.f` |
| `sqrt.approx.f32` | `@llvm.nvvm.sqrt.approx.f` |
| `rcp.approx.f32` | `@llvm.nvvm.rcp.approx.f` |
| `ex2.approx.f32` | `@llvm.nvvm.ex2.approx.f` |
| `lg2.approx.f32` | `@llvm.nvvm.lg2.approx.f` |
| `dp4a.u32.u32` | `@llvm.nvvm.idp4a.u.u` |
| `fma.rn.f16` | `@llvm.fma.f16` |
| `bar.warp.sync` | `@llvm.nvvm.bar.warp.sync(i32 -1)` |
| `mov.u32 %r, %tid.x` | `@llvm.nvvm.read.ptx.sreg.tid.x()` |
| `shfl.sync.up.b32` | `@__zluda_ptx_impl_shfl_sync_up_b32` ¹ |
| `atom.global.add` | `atomicrmw add` |

> ¹ warp shuffle / vote / 部分特殊操作仍通过 ZLUDA runtime stub 实现，链接 `ptx/lib/zluda_ptx_impl.bc` 后可解析为最终 NVVM intrinsic。

---

## 修改了哪些文件

相比 ZLUDA 原版（目标 AMD），以下文件被修改以输出 NVPTX IR：

| 文件 | 改动 |
|---|---|
| `ptx/src/pass/llvm/mod.rs` | `ParamEntry` 地址空间 4 → 101（NVPTX param space） |
| `ptx/src/pass/llvm/emit.rs` | 调用约定 AMDGPUKernel→PTXKernel；去掉 `amdgpu-*` 属性；`target-features`→`target-cpu=sm_xxx`；22 个 `llvm.amdgcn.*` → `llvm.nvvm.*`；`setreg`/`dcache.inv` no-op |
| `ptx/src/pass/mod.rs` | 特殊寄存器改为 `llvm.nvvm.read.ptx.sreg.*`（x/y/z 分立，无轴参数）；传递 sm_version 给 emit |
| `ptx/src/pass/fix_special_registers.rs` | `sreg_to_function` map 改为 `(sreg, axis)` 键，去掉轴常量参数传递 |
| `ptx/src/pass/replace_instructions_with_functions.rs` | rsqrt/sqrt/rcp/ex2/lg2 approx 改用 `llvm.nvvm.*` 完整名，`to_call` 跳过含 `.` 名称的 ZLUDA 前缀 |
| `llvm_zluda/build.rs` | 加 `CMAKE_SUPPRESS_REGENERATION=ON`，解决 cmake 时间戳循环问题 |
| `ext/highs-sys/build.rs` | 同上 |

---

## 已验证的 PTX 场景

| PTX | sm 版本 | 覆盖的指令 | IR 行数 |
|---|---|---|---|
| `vecadd.ptx` | sm_80 | ld/st global, fadd, tid/ctaid/ntid | ~100 |
| `layernorm.ptx` | sm_110 | rsqrt.approx, bar.sync, shared mem | 666 |
| `softmax_mt.ptx` | sm_110 | ex2.approx ×8, rcp.approx | 714 |
| `fused_ew.ptx` | sm_110 | rcp.approx, 4 轴特殊寄存器 | ~680 |
| `dp4a` 量化 | sm_110 | dp4a.u32.u32 | 53 |
| `f16 FMA` | sm_110 | fma.rn.f16, bitcast i16↔half | 57 |
| shfl.sync 全部变体（×34）| sm_110 | shfl.sync.{up,down,bfly,idx} | ~38 each |

---

## 注意事项

- **不支持**的 PTX 指令会导致 `parse error` 退出：`mbarrier`、`cp.async.bulk`（TMA）、`brx.idx`（计算跳转表）等 PTX ISA 9.x 新指令尚未在 ZLUDA parser 中实现。
- 生成的 IR **不包含** `!nvvm.annotations` metadata；LLVM NVPTX 后端通过 `ptx_kernel` 调用约定（CC 71）识别 kernel，无需 metadata。
- 若要将 IR 编译到 PTX/cubin，需要配套 NVPTX target 的 `llc`，或直接用 `nvcc -x ir input.bc`。

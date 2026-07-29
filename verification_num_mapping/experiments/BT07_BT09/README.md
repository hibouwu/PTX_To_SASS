# BT07 / BT09 B200 动态输入 A/B 复核

## 结论

| ID | PTX | 动态 O0 目标序列 | 动态 O3 目标序列 | 严格核心映射 |
|----|-----|------------------|------------------|--------------|
| BT07 | popc.b32 %r1, %r0; | LOP3.LUT → LOP3.LUT → POPC | POPC | 1:1 |
| BT09 | brev.b32 %r1, %r0; | BREV → SHF.R.U32.HI → SGXT.U32 | BREV | 1:1 |

BT07 的两条 `LOP3` 和 BT09 的 `SHF/SGXT` 都是 `ptxas -O0` lowering 中的输入或结果
规范化，不是目标 PTX 的必要核心动作。它们不应进入严格 PTX→SASS 核心展开规则。

## 环境

- GPU：NVIDIA B200，`sm_100a`
- GPU UUID：`GPU-30b7c1da-8725-7ec1-fa24-bc4fa38e731b`
- Driver：580.126.20
- `ptxas` / `nvdisasm`：CUDA 12.8，V12.8.93
- 复核日期：2026-07-23

## 实验设计

1. 重新编译原来的固定常量 PTX，确认旧 O0 序列可复现、旧 O3 会常量折叠。
2. 把源操作数改成 kernel 参数并把结果写到参数给出的 global 地址，防止 O3 常量折叠
   或删除结果。
3. 增加同构 `mov.b32` baseline，区分参数加载、结果 sink 与目标 bit 操作。
4. 分别用 `-O0`、`-O3` 和 `-lineinfo` 编译，再同时保存 `nvdisasm -g` 与 `-gp`。
5. 把 BT07、BT09 各自放进独立 PTX 再编译一次，排除同模块多 kernel 布局的影响。
6. 通过 CUDA Driver API 直接加载四个独立动态 cubin，在 B200 上执行 O0/O3 内核并核对
   输出值。

## 关键证据

动态 O3 的目标源行只包含一条核心指令：

```text
// BT07, PTX line 100
/*0040*/ POPC R5, UR6 ;

// BT09, PTX line 100
/*0040*/ BREV R5, R5 ;
```

随后两者都直接进入目标行之外的 `STG`。独立 PTX 与三内核同模块版本结果一致。

动态 O0 则稳定复现旧序列：

```text
BT07: LOP3.LUT → LOP3.LUT → POPC
BT09: BREV → SHF.R.U32.HI → SGXT.U32
```

这说明 O0 的 1:3 是优化级别相关的完整 lowering，而不是硬件核心映射必须为 1:3。

## 运行结果

| ID | 输入 | 期望输出 | O0 | O3 |
|----|------|----------|----|----|
| BT07 | 0xF0F00F01 | 13 | PASS | PASS |
| BT09 | 0x0000000D | 0xB0000000 | PASS | PASS |

这里运行的是上表所分析的同一组独立动态 cubin，而不是另行用 CUDA C++ 重新生成目标
指令。加载和调用代码见 `run_cubin.cpp`，原始终端结果保存在 `runtime_results.txt`。

## 产物

- `ptx/BT07_popc_b32_dynamic.ptx`、`ptx/BT09_brev_b32_dynamic.ptx`：独立动态输入用例
- `ptx/bt07_bt09_dynamic.ptx`：包含 `mov` baseline 与两个目标内核的同模块用例
- `cubin/`：固定输入、动态输入的 O0/O3 cubin
- `sass/*_O0.sass`、`sass/*_O3.sass`：`nvdisasm -g` 行号证据
- `sass/*_gp.sass`：`nvdisasm -gp` 原生 PTX/SASS 对照证据
- `run_cubin.cpp`、`runtime_results.txt`：直接加载 cubin 的执行校验程序与结果

主映射表中的旧固定输入 O3 仍显示“编译器优化消除”，因为其结果已被常量折叠；本次
动态输入 O3 才用于判断 BT07、BT09 的必要核心 opcode 数。

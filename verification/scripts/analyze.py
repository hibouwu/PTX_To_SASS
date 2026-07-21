#!/usr/bin/env python3
"""
PTX→SASS 1:1 映射验证 - 自动化分析脚本

解析 sass_dumps/ 中的反汇编输出, 与 ptx_sources/ 中的源文件对比,
自动判定每条指令的 PTX→SASS 映射关系.

输出: results/mapping_report.csv

用法: python3 scripts/analyze.py [--sass-dir sass_dumps] [--ptx-dir ptx_sources]
"""

import csv
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ===========================================================================
# 配置
# ===========================================================================

BASE_DIR = Path(__file__).resolve().parent.parent
PTX_DIR = BASE_DIR / "ptx_sources"
SASS_DIR = BASE_DIR / "sass_dumps"
RESULTS_DIR = BASE_DIR / "results"

# SASS 中应忽略的指令 (不计入有效指令数)
IGNORED_SASS_OPCODES = {
    "NOP",          # 对齐填充
    "EXIT",         # 函数退出 (对应 ret)
    "BRA",          # 分支 (单独考虑)
    "DEPBAR",       # 依赖屏障 (ptxas 插入)
    "WARPSYNC",     # warp 同步
}

# SASS 中标记为 "setup" 的前置指令 (参数加载等, 不计入待测指令展开)
SETUP_SASS_OPCODES = {
    "MOV",          # 参数搬移/常数加载
    "LDC",          # 常量内存加载 (参数)
    "S2R",          # 特殊寄存器读取 (如果不是待测指令)
    "IMAD",         # 地址计算 (ptxas 可能将 mov+add 合并)
    "SHF",          # shift (地址计算)
    "ULDC",         # uniform load constant
    "UMOV",         # uniform mov
    "USHF",         # uniform shift
    "UIADD3",       # uniform int add
    "UIMAD",        # uniform int mad
}

# GP 寄存器正则 (R0, R1, ..., R255; RZ 是零寄存器不计)
GP_REG_PATTERN = re.compile(r'\bR(\d+)\b')
# 谓词寄存器
PRED_REG_PATTERN = re.compile(r'\bP(\d+)\b')
# Uniform 寄存器
UNIFORM_REG_PATTERN = re.compile(r'\bUR(\d+)\b')


# ===========================================================================
# 数据结构
# ===========================================================================

@dataclass
class PTXInfo:
    """从 PTX 源文件提取的信息."""
    filepath: Path
    batch: str
    case_id: str
    mnemonic: str
    # 声明的寄存器总数 (按类型)
    reg_declarations: dict = field(default_factory=dict)
    # 待测指令行
    target_instruction: str = ""
    # 参数加载指令数 (ld.param 等)
    setup_instruction_count: int = 0


@dataclass
class SASSInfo:
    """从 SASS dump 提取的信息."""
    filepath: Path
    opt_level: str  # "O0" or "O3"
    # 全部有效 SASS 指令 (排除 NOP/EXIT)
    all_instructions: list = field(default_factory=list)
    # 待测区域的指令 (排除 setup)
    target_instructions: list = field(default_factory=list)
    # 使用的 GP 寄存器编号集合
    gp_registers_used: set = field(default_factory=set)
    # 使用的谓词寄存器
    pred_registers_used: set = field(default_factory=set)
    # 原始文本
    raw_text: str = ""


@dataclass
class AnalysisResult:
    """单个测试用例的分析结果."""
    batch: str
    case_id: str
    mnemonic: str
    instruction: str
    # PTX 侧
    ptx_reg_count: int = 0
    ptx_setup_count: int = 0
    # SASS O0 侧
    sass_total_instrs_O0: int = 0
    sass_target_instrs_O0: int = 0
    sass_gp_regs_O0: int = 0
    sass_extra_regs_O0: int = 0
    # SASS O3 侧
    sass_total_instrs_O3: int = 0
    sass_target_instrs_O3: int = 0
    sass_gp_regs_O3: int = 0
    sass_extra_regs_O3: int = 0
    # 判定
    verdict: str = "UNKNOWN"
    notes: str = ""


# ===========================================================================
# PTX 解析
# ===========================================================================

def parse_ptx_file(filepath: Path) -> PTXInfo:
    """解析 PTX 源文件, 提取寄存器声明和待测指令."""
    text = filepath.read_text(encoding="utf-8")

    # 提取 batch 和 case_id
    rel = filepath.relative_to(PTX_DIR)
    batch = rel.parts[0] if len(rel.parts) > 1 else ""
    stem = filepath.stem  # e.g. "T01_mma_cg1_tf32"
    parts = stem.split("_", 1)
    case_id = parts[0]
    mnemonic = parts[1] if len(parts) > 1 else stem

    info = PTXInfo(
        filepath=filepath,
        batch=batch,
        case_id=case_id,
        mnemonic=mnemonic,
    )

    # 计算 .reg 声明的寄存器数 (精确区分位宽)
    # 64-bit 类型占 2 个 SASS GP slot, 32-bit 占 1 个, pred 不占 GP
    reg_count = 0        # 名义寄存器数 (与 PTX 声明一致)
    sass_gp_slots = 0    # 预期 SASS GP slot 数

    for line in text.splitlines():
        line_stripped = line.strip()
        if not line_stripped.startswith(".reg"):
            continue

        # 提取类型: .reg .s64 ...  或 .reg .f64 ... 或 .reg .b64 ...
        type_match = re.search(r'\.reg\s+\.(\w+)\s+', line_stripped)
        if not type_match:
            continue
        ptx_type = type_match.group(1)

        # 判断是否为 64-bit 类型
        is_64bit = ptx_type.endswith("64")  # s64, u64, f64, b64
        is_pred = ptx_type == "pred"

        # 计算寄存器数量
        # 格式1: .reg .s32 %r<N>;  -> N 个寄存器
        m = re.search(r'%\w+<(\d+)>', line_stripped)
        if m:
            n = int(m.group(1))
        else:
            # 格式2: .reg .s32 %r0, %r1, %r2;  -> 逗号分隔
            n = line_stripped.count('%')

        reg_count += n
        if is_pred:
            pass  # predicate 不占 GP slot
        elif is_64bit:
            sass_gp_slots += n * 2
        else:
            sass_gp_slots += n

    info.reg_declarations = {"total": reg_count, "sass_gp_slots": sass_gp_slots}

    # 提取待测指令 (在 "// === 待测指令" 标记之后)
    lines = text.splitlines()
    in_target = False
    target_lines = []
    setup_count = 0
    for line in lines:
        stripped = line.strip()
        if "待测指令" in stripped:
            in_target = True
            continue
        if in_target and stripped and not stripped.startswith("//"):
            if stripped in ("ret;", "}", ""):
                break
            target_lines.append(stripped)

        # 计算 setup 指令数 (ld.param / mov 等在待测之前)
        if not in_target and stripped.startswith(("ld.param", "mov.")):
            setup_count += 1

    info.target_instruction = " | ".join(target_lines)
    info.setup_instruction_count = setup_count

    return info


# ===========================================================================
# SASS 解析
# ===========================================================================

def parse_sass_file(filepath: Path, opt_level: str) -> SASSInfo | None:
    """解析 cuobjdump -sass 的输出."""
    if not filepath.exists():
        return None

    text = filepath.read_text(encoding="utf-8")
    info = SASSInfo(filepath=filepath, opt_level=opt_level, raw_text=text)

    # cuobjdump 输出格式:
    # /*0000*/  IMAD.MOV.U32 R1, RZ, RZ, c[0x0][0x28] ;
    # /*0010*/  MOV R2, c[0x0][0x160] ;
    # 提取所有指令行
    instr_pattern = re.compile(
        r'/\*[0-9a-fA-F]+\*/\s+'   # 地址前缀
        r'(@[!]?P\d+\s+)?'         # 可选谓词
        r'([A-Z][A-Z0-9_.]+)'      # 操作码
        r'(.*);\s*$'               # 操作数
    )

    all_instrs = []
    for line in text.splitlines():
        line = line.strip()
        m = instr_pattern.match(line)
        if m:
            predicate = m.group(1) or ""
            opcode = m.group(2).strip()
            operands = m.group(3).strip()
            all_instrs.append({
                "predicate": predicate.strip(),
                "opcode": opcode,
                "operands": operands,
                "raw": line,
            })

    info.all_instructions = all_instrs

    # 提取 GP 寄存器使用
    gp_regs = set()
    pred_regs = set()
    for instr in all_instrs:
        full = instr["operands"] + " " + instr.get("predicate", "")
        for m in GP_REG_PATTERN.finditer(full):
            reg_num = int(m.group(1))
            gp_regs.add(reg_num)
        for m in PRED_REG_PATTERN.finditer(full):
            pred_regs.add(int(m.group(1)))

    info.gp_registers_used = gp_regs
    info.pred_registers_used = pred_regs

    # 分离 target 指令 vs setup 指令
    # 策略: 排除 IGNORED 和 SETUP opcodes 后的剩余为 target
    target_instrs = []
    for instr in all_instrs:
        base_opcode = instr["opcode"].split(".")[0]  # IMAD.MOV -> IMAD
        if base_opcode in IGNORED_SASS_OPCODES:
            continue
        # 不排除 SETUP, 因为有些 setup opcode 也是待测指令
        target_instrs.append(instr)

    info.target_instructions = target_instrs

    return info


# ===========================================================================
# 分析逻辑
# ===========================================================================

def compute_expected_sass_regs(ptx_info: PTXInfo) -> int:
    """估算 SASS 中预期使用的 GP 寄存器数.

    包括:
    - PTX 中声明的寄存器 (64-bit 占 2 个 GP slot)
    - ptxas 用于参数加载的寄存器 (ld.param 通常映射为 LDC/MOV)
    - R1 通常被 ptxas 保留为栈指针
    """
    # 简单估算: PTX 声明数 + setup 寄存器 + 1 (R1 栈指针)
    # 实际比较时用差值, 这里只做参考
    return ptx_info.reg_declarations.get("total", 0)


def classify_result(result: AnalysisResult) -> str:
    """根据分析数据判定映射类别."""
    # 特殊标记: 如果 O0 SASS 文件不存在 (编译失败)
    if result.sass_total_instrs_O0 == -1:
        return "COMPILE_FAIL"

    target_O0 = result.sass_target_instrs_O0
    extra_O0 = result.sass_extra_regs_O0
    target_O3 = result.sass_target_instrs_O3

    # 对于只有一条 setup + 一条 target 的简单 kernel:
    # 去掉 param load 后, 理想情况是 1 条 SASS 对应待测指令
    # 但由于 ptxas 会加入 param load 指令, 需要更宽松的判定

    # 判定: 如果待测指令区域只有 <= setup_count + 1 条有效指令
    # 且无额外寄存器, 则为 1:1

    # 简化判定 (保守):
    # - target_O0 <= ptx_setup + 待测指令数 且 extra_regs == 0 -> 1:1
    # - 否则需人工审查

    ptx_setup = result.ptx_setup_count
    # 注意: 有些测试包含多条待测指令 (如 I17 包含 and/or/xor 三条)
    target_instr_count = result.instruction.count(";") if result.instruction else 1
    expected_sass_count = ptx_setup + target_instr_count

    if target_O0 <= 0:
        return "NEEDS_REVIEW"

    # 核心判定
    if target_O0 <= expected_sass_count + 2 and extra_O0 <= 1:
        # 允许 +2 的余量: ptxas 可能插入 IMAD 地址计算或 MOV 常数
        if extra_O0 == 0:
            return "1:1"
        else:
            return "1:1_FORMAT"
    elif target_O0 > expected_sass_count + 5:
        # 明显展开
        if result.sass_total_instrs_O3 != -1:
            # O3 也展开 -> 架构强制
            if target_O3 > expected_sass_count + 3:
                return "EXPAND_ARCH"
            else:
                return "EXPAND_OPT"
        return "EXPAND_ARCH"
    else:
        return "NEEDS_REVIEW"


def analyze_case(ptx_info: PTXInfo, sass_dir: Path = SASS_DIR) -> AnalysisResult:
    """分析单个测试用例."""
    result = AnalysisResult(
        batch=ptx_info.batch,
        case_id=ptx_info.case_id,
        mnemonic=ptx_info.mnemonic,
        instruction=ptx_info.target_instruction,
        ptx_reg_count=ptx_info.reg_declarations.get("total", 0),
        ptx_setup_count=ptx_info.setup_instruction_count,
    )

    # 构造 SASS 文件路径
    # 命名规则: {batch}__{case_id}_{mnemonic}_{O0|O3}.sass
    sass_stem = f"{ptx_info.batch}__{ptx_info.case_id}_{ptx_info.mnemonic}"
    sass_O0_path = sass_dir / f"{sass_stem}_O0.sass"
    sass_O3_path = sass_dir / f"{sass_stem}_O3.sass"

    # 解析 O0
    sass_O0 = parse_sass_file(sass_O0_path, "O0")
    if sass_O0:
        result.sass_total_instrs_O0 = len(sass_O0.all_instructions)
        result.sass_target_instrs_O0 = len(sass_O0.target_instructions)
        result.sass_gp_regs_O0 = len(sass_O0.gp_registers_used)
        # 额外寄存器 = SASS GP slot 总数 - 预期 GP slot 数
        # 预期: PTX 声明的 sass_gp_slots (64-bit x2) + 1 (R1 栈指针)
        expected = ptx_info.reg_declarations.get("sass_gp_slots",
                   ptx_info.reg_declarations.get("total", 0))
        result.sass_extra_regs_O0 = max(0, len(sass_O0.gp_registers_used) - expected - 1)
    else:
        result.sass_total_instrs_O0 = -1
        result.sass_target_instrs_O0 = -1
        result.notes += "O0 SASS not found; "

    # 解析 O3
    sass_O3 = parse_sass_file(sass_O3_path, "O3")
    if sass_O3:
        result.sass_total_instrs_O3 = len(sass_O3.all_instructions)
        result.sass_target_instrs_O3 = len(sass_O3.target_instructions)
        result.sass_gp_regs_O3 = len(sass_O3.gp_registers_used)
        expected = ptx_info.reg_declarations.get("sass_gp_slots",
                   ptx_info.reg_declarations.get("total", 0))
        result.sass_extra_regs_O3 = max(0, len(sass_O3.gp_registers_used) - expected - 1)
    else:
        result.sass_total_instrs_O3 = -1
        result.sass_target_instrs_O3 = -1
        result.notes += "O3 SASS not found; "

    # 判定
    result.verdict = classify_result(result)

    return result


# ===========================================================================
# 报告生成
# ===========================================================================

REPORT_FIELDS = [
    "batch", "case_id", "mnemonic", "instruction",
    "ptx_reg_count", "ptx_setup_count",
    "sass_total_instrs_O0", "sass_target_instrs_O0",
    "sass_gp_regs_O0", "sass_extra_regs_O0",
    "sass_total_instrs_O3", "sass_target_instrs_O3",
    "sass_gp_regs_O3", "sass_extra_regs_O3",
    "verdict", "notes",
]


def generate_report(results: list[AnalysisResult], output_path: Path):
    """生成 CSV 报告."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "batch": r.batch,
                "case_id": r.case_id,
                "mnemonic": r.mnemonic,
                "instruction": r.instruction[:80],  # 截断过长内容
                "ptx_reg_count": r.ptx_reg_count,
                "ptx_setup_count": r.ptx_setup_count,
                "sass_total_instrs_O0": r.sass_total_instrs_O0,
                "sass_target_instrs_O0": r.sass_target_instrs_O0,
                "sass_gp_regs_O0": r.sass_gp_regs_O0,
                "sass_extra_regs_O0": r.sass_extra_regs_O0,
                "sass_total_instrs_O3": r.sass_total_instrs_O3,
                "sass_target_instrs_O3": r.sass_target_instrs_O3,
                "sass_gp_regs_O3": r.sass_gp_regs_O3,
                "sass_extra_regs_O3": r.sass_extra_regs_O3,
                "verdict": r.verdict,
                "notes": r.notes,
            })

    print(f"Report written to: {output_path}")


def print_summary(results: list[AnalysisResult]):
    """打印汇总统计."""
    verdicts = {}
    for r in results:
        verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1

    print("\n" + "=" * 60)
    print("ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"  Total test cases:     {len(results)}")
    print("")
    print("  Verdict distribution:")
    for v in sorted(verdicts.keys()):
        count = verdicts[v]
        pct = 100.0 * count / len(results) if results else 0
        print(f"    {v:20s}  {count:3d}  ({pct:.1f}%)")

    print("")

    # 列出需要关注的 cases
    expand_cases = [r for r in results if "EXPAND" in r.verdict]
    review_cases = [r for r in results if r.verdict == "NEEDS_REVIEW"]
    fail_cases = [r for r in results if r.verdict == "COMPILE_FAIL"]

    if expand_cases:
        print("  EXPAND cases (require attention):")
        for r in expand_cases:
            print(f"    [{r.batch}] {r.case_id} {r.mnemonic}: "
                  f"O0={r.sass_target_instrs_O0} instrs, "
                  f"+{r.sass_extra_regs_O0} regs -> {r.verdict}")

    if review_cases:
        print("\n  NEEDS_REVIEW cases (manual inspection required):")
        for r in review_cases:
            print(f"    [{r.batch}] {r.case_id} {r.mnemonic}: "
                  f"O0={r.sass_target_instrs_O0} instrs, "
                  f"+{r.sass_extra_regs_O0} regs")

    if fail_cases:
        print("\n  COMPILE_FAIL cases:")
        for r in fail_cases:
            print(f"    [{r.batch}] {r.case_id} {r.mnemonic}")

    print("\n" + "=" * 60)

    # 最终结论建议
    one_to_one = sum(1 for r in results if r.verdict in ("1:1", "1:1_FORMAT"))
    total_valid = sum(1 for r in results if r.verdict != "COMPILE_FAIL")
    if total_valid > 0:
        ratio = 100.0 * one_to_one / total_valid
        print(f"\n  1:1 Mapping Rate: {one_to_one}/{total_valid} ({ratio:.1f}%)")
        if ratio == 100.0:
            print("  CONCLUSION: All instructions are 1:1. "
                  "L0 can remove 1->N expansion logic entirely.")
        elif ratio >= 90.0:
            print("  CONCLUSION: Most instructions are 1:1. "
                  "Non-1:1 cases can be excluded from whitelist.")
        else:
            print("  CONCLUSION: Significant expansion exists. "
                  "L0 expansion logic may need to be retained.")


# ===========================================================================
# Main
# ===========================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="PTX→SASS mapping analysis")
    parser.add_argument("--ptx-dir", type=Path, default=PTX_DIR)
    parser.add_argument("--sass-dir", type=Path, default=SASS_DIR)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "mapping_report.csv")
    parser.add_argument("--ptx-only", action="store_true",
                        help="Only parse PTX files (skip SASS analysis)")
    args = parser.parse_args()

    ptx_dir = args.ptx_dir
    sass_dir = args.sass_dir

    # 收集所有 PTX 文件
    ptx_files = sorted(ptx_dir.rglob("*.ptx"))
    if not ptx_files:
        print(f"ERROR: No .ptx files found in {ptx_dir}")
        sys.exit(1)

    print(f"Found {len(ptx_files)} PTX test cases.")
    print(f"SASS directory: {sass_dir}")
    print("")

    # 解析 PTX
    results = []
    for ptx_file in ptx_files:
        ptx_info = parse_ptx_file(ptx_file)
        # 覆盖路径为实际命令行传入的目录
        ptx_info.filepath = ptx_file

        if args.ptx_only:
            print(f"  [{ptx_info.batch}] {ptx_info.case_id}: "
                  f"regs={ptx_info.reg_declarations.get('total', 0)}, "
                  f"setup={ptx_info.setup_instruction_count}, "
                  f"target='{ptx_info.target_instruction[:60]}'")
            continue

        # 分析
        result = analyze_case(ptx_info, sass_dir)
        results.append(result)

        # 实时输出
        status_icon = {
            "1:1": "[OK]",
            "1:1_FORMAT": "[OK]",
            "EXPAND_ARCH": "[!!]",
            "EXPAND_OPT": "[!?]",
            "NEEDS_REVIEW": "[??]",
            "COMPILE_FAIL": "[XX]",
            "UNKNOWN": "[--]",
        }.get(result.verdict, "[--]")

        print(f"  {status_icon} [{result.batch}] {result.case_id} "
              f"{result.mnemonic}: {result.verdict}")

    if args.ptx_only:
        print(f"\nPTX-only mode: parsed {len(ptx_files)} files.")
        return

    # 生成报告
    generate_report(results, args.output)
    print_summary(results)


if __name__ == "__main__":
    main()

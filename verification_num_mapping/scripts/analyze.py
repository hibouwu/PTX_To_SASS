#!/usr/bin/env python3
"""
PTX→SASS 1:1 映射验证 - 自动化分析脚本

解析 sass_dumps/ 中的反汇编输出, 与 ptx_sources/ 中的源文件对比,
自动判定每条指令的 PTX→SASS 映射关系.

输出: results/mapping_report.csv

用法: python3 scripts/analyze.py [--sass-dir sass_dumps] [--ptx-dir ptx_sources]
"""

import collections
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
    # 非法但有研究价值的负向用例（例如规范未定义的 opcode/type 组合）
    unsupported_reason: str = ""


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
    # True when scheduling makes source line 100 reappear after another line.
    source_locations_interleaved: bool = False


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
    sass_sequence_O0: str = ""
    sass_core_instrs_O0: int = 0
    sass_core_sequence_O0: str = ""
    core_filter_notes_O0: str = ""
    # SASS O3 侧
    sass_total_instrs_O3: int = 0
    sass_target_instrs_O3: int = 0
    sass_gp_regs_O3: int = 0
    sass_extra_regs_O3: int = 0
    sass_sequence_O3: str = ""
    sass_core_instrs_O3: int = 0
    sass_core_sequence_O3: str = ""
    core_filter_notes_O3: str = ""
    # 人工审计口径：仅在规则已由具体 SASS 证据确认时填写。
    audited_sass_instrs_O0: int = -1
    audited_sass_sequence_O0: str = ""
    audit_status: str = "PENDING"
    audit_verdict: str = "PENDING"
    audit_notes: str = ""
    # 判定
    raw_verdict: str = "UNKNOWN"
    cleaned_verdict: str = "UNKNOWN"
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

    unsupported_match = re.search(
        r"^\s*//\s*EXPECTED_UNSUPPORTED_BY_PTX_ISA:\s*(.+)$",
        text,
        re.MULTILINE,
    )
    if unsupported_match:
        info.unsupported_reason = unsupported_match.group(1).strip()

    # 提取待测指令 (在 ASCII marker 之后；ptxas rejects non-ASCII PTX text)
    lines = text.splitlines()
    in_target = False
    target_lines = []
    setup_count = 0
    for line in lines:
        stripped = line.strip()
        if in_target and "end target instruction" in stripped:
            break
        if "target instruction" in stripped:
            in_target = True
            continue
        if in_target and stripped.startswith(".loc "):
            continue
        if in_target and stripped and not stripped.startswith("//"):
            if stripped == "}":
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
        r'(@[!]?(?:P\d+|UP\d+|PT|UPT)\s+)?'  # 可选普通/统一/恒真谓词
        r'([A-Z][A-Z0-9_.]+)'      # 操作码
        r'(.*);\s*$'               # 操作数
    )
    instruction_like_pattern = re.compile(r'/\*[0-9a-fA-F]+\*/')

    all_instrs = []
    unparsed_instruction_lines = []
    source_line = None
    source_line_events = []
    for line in text.splitlines():
        line = line.strip()
        line_match = re.match(r'//## File ".*", line (\d+)', line)
        if line_match:
            source_line = int(line_match.group(1))
            source_line_events.append(source_line)
            continue
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
                "source_line": source_line,
            })
        elif instruction_like_pattern.match(line) and line.endswith(";"):
            unparsed_instruction_lines.append(line)

    if unparsed_instruction_lines:
        sample = "\n  ".join(unparsed_instruction_lines[:5])
        raise ValueError(
            f"Unparsed SASS instruction line(s) in {filepath}: "
            f"{len(unparsed_instruction_lines)}\n  {sample}"
        )

    info.all_instructions = all_instrs
    target_event_indices = [
        index for index, event in enumerate(source_line_events) if event == 100
    ]
    if target_event_indices:
        first_target = target_event_indices[0]
        last_target = target_event_indices[-1]
        info.source_locations_interleaved = (
            200 in source_line_events[:first_target]
            or any(
                event != 100
                for event in source_line_events[first_target:last_target + 1]
            )
        )

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

    # The generator assigns the target PTX statement(s) to .loc line 100.
    # nvdisasm -g propagates that source location to every lowered SASS op.
    info.target_instructions = [
        instr for instr in all_instrs if instr["source_line"] == 100
    ]

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


def recover_coalesced_source_location(ptx_info: PTXInfo, sass_info: SASSInfo) -> bool:
    """Recover targets whose SASS was attributed to the preceding setup line.

    ptxas can fuse unary packed-half operations with operand modifiers and retain
    the source location of the producing setup instruction. These signatures
    were established by direct inspection of the B200 nvdisasm output. A match
    is deliberately strict so an unrelated setup instruction is never claimed.
    """
    if sass_info.target_instructions:
        return False

    instruction = ptx_info.target_instruction
    if instruction.startswith("neg.f16x2 "):
        predicate = lambda item: (
            item["opcode"] == "HADD2"
            and "-RZ.H0_H0" in item["operands"]
            and re.search(r",\s*-R\d+,", item["operands"])
        )
    elif instruction.startswith("abs.f16x2 "):
        predicate = lambda item: (
            item["opcode"] == "HADD2"
            and "-RZ.H0_H0" in item["operands"]
            and re.search(r",\s*\|R\d+\|,", item["operands"])
        )
    else:
        return False

    candidates = [
        item for item in sass_info.all_instructions
        if item["source_line"] == 10 and predicate(item)
    ]
    if len(candidates) != 1:
        return False
    sass_info.target_instructions = candidates
    return True


def _is_identity_move(item: dict) -> bool:
    """Return true for a register self-move with no architectural effect."""
    if item["opcode"] not in {"MOV", "UMOV"}:
        return False
    operands = [part.strip() for part in item["operands"].split(",")]
    return len(operands) == 2 and operands[0] == operands[1]


def _is_identity_iadd3(item: dict) -> bool:
    """Return true for an IADD3 used only as an O0 register self-copy."""
    opcode = item["opcode"]
    if opcode not in {"IADD3", "UIADD3"}:
        return False
    operands = [part.strip() for part in item["operands"].split(",")]
    if len(operands) != 6:
        return False
    destination, pred_out_1, pred_out_2, *sources = operands
    expected_pred = "UPT" if opcode == "UIADD3" else "PT"
    zero = "URZ" if opcode == "UIADD3" else "RZ"
    return (
        pred_out_1 == expected_pred
        and pred_out_2 == expected_pred
        and sources.count(destination) == 1
        and sources.count(zero) == 2
    )


def clean_target_instructions(ptx_info: PTXInfo, instructions: list) -> tuple[list, str]:
    """Remove only proven non-semantic scaffolding from a raw sequence."""
    cleaned = []
    removed = []
    target_is_mov = ptx_info.target_instruction.lstrip().startswith("mov.")
    preserve_identity_mov = target_is_mov and not any(
        item["opcode"] not in {"MOV", "UMOV", "NOP"}
        and not _is_identity_iadd3(item)
        for item in instructions
    )

    for item in instructions:
        if item["opcode"] == "NOP":
            removed.append("NOP")
            continue
        if _is_identity_move(item) and not preserve_identity_mov:
            removed.append("identity MOV")
            continue
        if _is_identity_iadd3(item):
            removed.append("identity IADD3")
            continue
        if (
            cleaned
            and item["opcode"] == "WARPSYNC.ALL"
            and cleaned[-1]["opcode"] == "WARPSYNC.ALL"
        ):
            removed.append("duplicate WARPSYNC.ALL")
            continue
        if preserve_identity_mov and _is_identity_move(item):
            signature = (item["opcode"], item["operands"])
            if any(
                (previous["opcode"], previous["operands"]) == signature
                for previous in cleaned
            ):
                removed.append("duplicate target MOV")
                continue
        cleaned.append(item)

    if (
        ptx_info.target_instruction.lstrip().startswith("ret;")
        and any(item["opcode"] == "EXIT" for item in cleaned)
    ):
        without_exit_trap = [
            item for item in cleaned
            if not (item["opcode"] == "BRA" and ".L_x_0" in item["operands"])
        ]
        if len(without_exit_trap) != len(cleaned):
            removed.append("post-EXIT trap BRA")
            cleaned = without_exit_trap

    counts = collections.Counter(removed)
    notes = ", ".join(
        f"removed {count} {name}" for name, count in counts.items()
    )
    return cleaned, notes


def format_sass_instruction(item: dict) -> str:
    """Render a parsed SASS instruction without dropping its predicate."""
    prefix = f'{item["predicate"]} ' if item["predicate"] else ""
    return f'{prefix}{item["opcode"]} {item["operands"]}'.strip()


def audit_semantic_sequence(
    ptx_info: PTXInfo, core_instructions: list
) -> tuple[list, str, str]:
    """Return a manually justified semantic sequence for audited families.

    This layer is intentionally allow-list based.  A source-line association is
    not enough to prove that an instruction implements the target PTX: ptxas can
    attribute address construction, operand routing, and result copies to line
    100.  Until a family has an explicit rule here, its audit status remains
    PENDING and the conservative core evidence is left untouched.
    """
    selected = []
    notes = ""

    if ptx_info.batch == "01_tcgen05" and ptx_info.case_id in {"T05", "T06", "T07"}:
        terminal_prefix = "STTM" if ptx_info.case_id == "T07" else "LDTM"
        selected = [
            item for item in core_instructions
            if item["opcode"] == "WARPSYNC.ALL"
            or item["opcode"] == "R2UR"
            or item["opcode"].startswith(terminal_prefix)
        ]
        expected = ["WARPSYNC.ALL", "R2UR", terminal_prefix]
        actual = [
            terminal_prefix if item["opcode"].startswith(terminal_prefix)
            else item["opcode"]
            for item in selected
        ]
        if actual != expected:
            return [], "PENDING", "tcgen05 ld/st protocol signature mismatch"
        notes = "verified tcgen05 ld/st protocol: warp sync + R-to-UR routing + TMEM opcode"

    elif ptx_info.batch == "01_tcgen05":
        if ptx_info.case_id == "T11":
            selected = []
            notes = "verified zero-core lowering: tcgen05 fence produced only NOP"
        elif ptx_info.case_id in {"T08", "T09"}:
            start = next(
                (
                    index for index, item in enumerate(core_instructions)
                    if item["opcode"] == "WARPSYNC.ALL"
                ),
                None,
            )
            if start is None:
                return [], "PENDING", "tcgen05 alloc/dealloc protocol has no WARPSYNC"
            selected = core_instructions[start:]
            notes = (
                "verified tcgen05 allocation guardrail protocol; excluded input/shared-address setup"
            )
        else:
            protocol_prefixes = (
                "R2UR", "VOTEU.", "PLOP3.", "ELECT", "UTCHMMA",
                "UTCQMMA", "UTCIMMA", "UTCCP", "UTCBAR", "BRA",
            )
            selected = [
                item for item in core_instructions
                if item["opcode"].startswith(protocol_prefixes)
            ]
            if not any(item["opcode"].startswith("UTC") for item in selected):
                return [], "PENDING", "tcgen05 protocol has no UTC execution opcode"
            notes = (
                "verified tcgen05 uniform/election protocol; excluded input predicate, "
                "coordinate, and shared-address setup"
            )

    elif ptx_info.batch == "02_tma":
        protocol_prefixes = (
            "R2UR", "PLOP3.", "ELECT", "UTMA", "LDGSTS", "DEPBAR", "BRA",
        )
        selected = [
            item for item in core_instructions
            if item["opcode"].startswith(protocol_prefixes)
        ]
        execution_prefixes = ("UTMA", "LDGSTS", "DEPBAR")
        if not any(item["opcode"].startswith(execution_prefixes) for item in selected):
            return [], "PENDING", "TMA protocol has no execution opcode"
        notes = (
            "verified TMA uniform/election protocol; excluded shared-address and coordinate setup"
        )

    elif ptx_info.batch == "07_lsu":
        instruction = ptx_info.target_instruction
        if instruction.startswith("ld.shared"):
            opcode_prefix = "LDS"
        elif instruction.startswith("st.shared"):
            opcode_prefix = "STS"
        elif instruction.startswith("ld.global"):
            opcode_prefix = "LDG"
        elif instruction.startswith("st.global"):
            opcode_prefix = "STG"
        elif instruction.startswith("ld.param"):
            opcode_prefix = "LDC"
        else:
            return [], "PENDING", "LSU target has no audited opcode rule"
        selected = [
            item for item in core_instructions
            if item["opcode"].startswith(opcode_prefix)
        ]
        if len(selected) != 1:
            return [], "PENDING", f"expected one {opcode_prefix} opcode, found {len(selected)}"
        notes = (
            f"verified {opcode_prefix} execution opcode; excluded address/descriptor "
            "preparation and result routing"
        )

    elif ptx_info.batch == "10_atomic":
        instruction = ptx_info.target_instruction
        if instruction.startswith("atom.global"):
            opcode_prefix = "ATOMG"
        elif instruction.startswith("atom.shared"):
            opcode_prefix = "ATOMS"
        elif instruction.startswith("red.global"):
            opcode_prefix = "REDG"
        else:
            return [], "PENDING", "atomic target has no audited opcode rule"
        selected = [
            item for item in core_instructions
            if item["opcode"].startswith(opcode_prefix)
        ]
        if len(selected) != 1:
            return [], "PENDING", f"expected one {opcode_prefix} opcode, found {len(selected)}"
        notes = (
            f"verified {opcode_prefix} execution opcode; excluded address/descriptor preparation"
        )

    elif ptx_info.batch in {
        "05_cuda_core_int",
        "06_cuda_core_fp",
        "11_half_precision",
        "12_bf16",
        "14_bit_ops",
        "17_quantization",
        "18_activation",
    }:
        # These batches have register/immediate operands only.  After the
        # conservative NOP/identity cleanup there is no address-construction or
        # descriptor scaffold to subtract.  Multi-op sequences (64-bit lane
        # splits, div/rem, exact f64 reciprocal/sqrt, fns, packed activation)
        # are therefore genuine lowering evidence, including non-identity MOVs
        # used to route intermediate values.
        selected = list(core_instructions)
        notes = (
            "verified register/immediate lowering; retained width splits, "
            "software expansion, and intermediate-value routing"
        )

    elif ptx_info.batch == "03_mbarrier":
        selected = [
            item for item in core_instructions
            if item["opcode"].startswith("SYNCS.")
        ]
        if len(selected) != 1:
            return [], "PENDING", f"expected one SYNCS opcode, found {len(selected)}"
        notes = "verified SYNCS execution opcode; excluded shared-address and operand encoding"

    elif ptx_info.batch == "04_fence":
        # Fence and cluster-barrier fallbacks are control protocols rather than
        # operand-address scaffolding.  Keep every conservatively cleaned op.
        selected = list(core_instructions)
        notes = "verified fence/barrier protocol; retained architecture fallback control flow"

    elif ptx_info.batch == "08_control_flow":
        selected = list(core_instructions)
        notes = "verified direct special-register/control-flow lowering"

    elif ptx_info.batch == "13_warp_comm":
        if ptx_info.unsupported_reason:
            return [], "NOT_APPLICABLE", ptx_info.unsupported_reason
        semantic_prefixes = ("SHFL.", "REDUX.", "CREDUX.", "VOTE.", "MATCH.")
        selected = [
            item for item in core_instructions
            if item["opcode"].startswith("WARPSYNC.COLLECTIVE")
            or item["opcode"] == "ENDCOLLECTIVE"
            or item["opcode"].startswith(semantic_prefixes)
            or (item["opcode"] == "ELECT" and ptx_info.case_id == "W14")
            or (
                item["opcode"] == "MOV"
                and "UR79" in item["operands"]
                and ptx_info.case_id in {"W05", "W06", "W08", "W09", "W14"}
            )
        ]
        expected_counts = {
            "W01": 3, "W02": 3, "W03": 3, "W04": 3,
            "W05": 4, "W06": 4, "W08": 4, "W09": 4,
            "W10": 3, "W11": 3, "W12": 3, "W13": 3, "W14": 4,
        }
        expected = expected_counts.get(ptx_info.case_id)
        if expected is None or len(selected) != expected:
            return [], "PENDING", (
                f"warp collective signature mismatch: expected {expected}, found {len(selected)}"
            )
        notes = (
            "verified warp collective protocol; excluded input/mask setup and predicate normalization"
        )

    elif ptx_info.batch == "15_cluster_dsmem" and ptx_info.case_id != "CL03":
        prefixes = {
            "CL01": ("PRMT",),
            "CL02": ("SHF.L.U64.HI",),
            "CL04": ("QSPC",),
            "CL05": ("LD.E",),
            "CL06": ("ST.E",),
        }[ptx_info.case_id]
        selected = [
            item for item in core_instructions
            if item["opcode"].startswith(prefixes)
        ]
        if len(selected) != 1:
            return [], "PENDING", f"cluster opcode signature mismatch: found {len(selected)}"
        notes = "verified cluster execution opcode; excluded address-space encoding preparation"

    elif ptx_info.batch == "15_cluster_dsmem" and ptx_info.case_id == "CL03":
        # The first MOV/S2R/LEA triple materializes the test fixture's static
        # shared symbol.  Everything after it is the u32 shared -> u64 generic
        # address conversion and O0 register routing.
        lea_index = next(
            (
                index for index, item in enumerate(core_instructions)
                if item["opcode"].startswith("LEA")
            ),
            None,
        )
        if lea_index is None or lea_index + 1 >= len(core_instructions):
            return [], "PENDING", "cvta.shared conversion signature mismatch"
        selected = core_instructions[lea_index + 1:]
        if not any(
            item["opcode"] == "S2R" and "SR_SWINHI" in item["operands"]
            for item in selected
        ):
            return [], "PENDING", "cvta.shared conversion lacks SR_SWINHI read"
        notes = (
            "verified shared-to-generic address conversion and O0 result routing; "
            "excluded static shared-symbol construction"
        )

    elif ptx_info.batch == "16_megakernel_ctrl":
        if ptx_info.case_id == "MK01":
            selected = [
                item for item in core_instructions
                if item["opcode"].startswith("WARPSYNC.COLLECTIVE")
                or item["opcode"] == "ENDCOLLECTIVE"
            ]
            if len(selected) != 2:
                return [], "PENDING", "bar.warp collective signature mismatch"
            notes = "verified bar.warp collective begin/end protocol; excluded mask setup"
        else:
            selected = list(core_instructions)
            notes = "verified direct megakernel-control lowering"

    else:
        return [], "PENDING", "family not yet manually audited"

    return selected, "VERIFIED", notes


def classify_count(count: int, result: AnalysisResult, ptx_info: PTXInfo) -> str:
    """根据分析数据判定映射类别."""
    if ptx_info.unsupported_reason:
        return "UNSUPPORTED_BY_PTX_ISA"

    # 特殊标记: 如果 O0 SASS 文件不存在 (编译失败)
    if result.sass_total_instrs_O0 == -1:
        return "COMPILE_FAIL"

    target_instr_count = result.instruction.count(";") if result.instruction else 1

    if count == 0:
        return "ELIMINATED"
    if count == target_instr_count:
        return "1:1"
    if count > target_instr_count:
        return "1:N"
    return "NEEDS_REVIEW"


def classify_core_result(result: AnalysisResult, ptx_info: PTXInfo) -> str:
    """Classify the cleaned core while preserving zero-cost lowering evidence."""
    verdict = classify_count(result.sass_core_instrs_O0, result, ptx_info)
    if (
        verdict == "ELIMINATED"
        and result.sass_target_instrs_O0 > 0
        and not ptx_info.unsupported_reason
    ):
        return "NO_CORE_SASS"
    return verdict


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
    if ptx_info.unsupported_reason:
        result.audit_status = "NOT_APPLICABLE"
        result.audit_verdict = "UNSUPPORTED_BY_PTX_ISA"
        result.audit_notes = ptx_info.unsupported_reason

    # 构造 SASS 文件路径
    # 命名规则: {batch}__{case_id}_{mnemonic}_{O0|O3}.sass
    sass_stem = f"{ptx_info.batch}__{ptx_info.case_id}_{ptx_info.mnemonic}"
    sass_O0_path = sass_dir / f"{sass_stem}_O0.sass"
    sass_O3_path = sass_dir / f"{sass_stem}_O3.sass"

    # 解析 O0
    sass_O0 = parse_sass_file(sass_O0_path, "O0")
    if sass_O0:
        if recover_coalesced_source_location(ptx_info, sass_O0):
            result.notes += "O0 target source location coalesced into setup line 10; "
        result.sass_total_instrs_O0 = len(sass_O0.all_instructions)
        result.sass_target_instrs_O0 = len(sass_O0.target_instructions)
        result.sass_gp_regs_O0 = len(sass_O0.gp_registers_used)
        result.sass_sequence_O0 = " | ".join(
            format_sass_instruction(instr) for instr in sass_O0.target_instructions
        )
        core_O0, result.core_filter_notes_O0 = clean_target_instructions(
            ptx_info, sass_O0.target_instructions
        )
        result.sass_core_instrs_O0 = len(core_O0)
        result.sass_core_sequence_O0 = " | ".join(
            format_sass_instruction(instr) for instr in core_O0
        )
        audited_O0, result.audit_status, result.audit_notes = audit_semantic_sequence(
            ptx_info, core_O0
        )
        if result.audit_status == "VERIFIED":
            result.audited_sass_instrs_O0 = len(audited_O0)
            result.audited_sass_sequence_O0 = " | ".join(
                format_sass_instruction(instr) for instr in audited_O0
            )
            result.audit_verdict = classify_count(
                result.audited_sass_instrs_O0, result, ptx_info
            )
            if (
                result.audit_verdict == "ELIMINATED"
                and result.sass_target_instrs_O0 > 0
            ):
                result.audit_verdict = "NO_CORE_SASS"
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
        if sass_O3.source_locations_interleaved:
            result.notes += (
                "O3 source locations interleaved by scheduling; "
                "O3 core sequence is advisory only; "
            )
        if recover_coalesced_source_location(ptx_info, sass_O3):
            result.notes += "O3 target source location coalesced into setup line 10; "
        result.sass_total_instrs_O3 = len(sass_O3.all_instructions)
        result.sass_target_instrs_O3 = len(sass_O3.target_instructions)
        result.sass_gp_regs_O3 = len(sass_O3.gp_registers_used)
        result.sass_sequence_O3 = " | ".join(
            format_sass_instruction(instr) for instr in sass_O3.target_instructions
        )
        core_O3, result.core_filter_notes_O3 = clean_target_instructions(
            ptx_info, sass_O3.target_instructions
        )
        result.sass_core_instrs_O3 = len(core_O3)
        result.sass_core_sequence_O3 = " | ".join(
            format_sass_instruction(instr) for instr in core_O3
        )
        expected = ptx_info.reg_declarations.get("sass_gp_slots",
                   ptx_info.reg_declarations.get("total", 0))
        result.sass_extra_regs_O3 = max(0, len(sass_O3.gp_registers_used) - expected - 1)
    else:
        result.sass_total_instrs_O3 = -1
        result.sass_target_instrs_O3 = -1
        result.notes += "O3 SASS not found; "

    # 判定
    if ptx_info.unsupported_reason:
        result.notes += f"{ptx_info.unsupported_reason}; "
    result.raw_verdict = classify_count(
        result.sass_target_instrs_O0, result, ptx_info
    )
    result.cleaned_verdict = classify_core_result(result, ptx_info)
    if result.audit_status == "VERIFIED":
        result.verdict = result.audit_verdict
    elif result.audit_status == "NOT_APPLICABLE" and ptx_info.unsupported_reason:
        result.verdict = "UNSUPPORTED_BY_PTX_ISA"
    else:
        result.verdict = result.cleaned_verdict

    return result


# ===========================================================================
# 报告生成
# ===========================================================================

REPORT_FIELDS = [
    "batch", "case_id", "mnemonic", "instruction",
    "ptx_reg_count", "ptx_setup_count",
    "sass_total_instrs_O0", "sass_target_instrs_O0",
    "sass_gp_regs_O0", "sass_extra_regs_O0",
    "sass_sequence_O0", "sass_core_instrs_O0", "sass_core_sequence_O0",
    "core_filter_notes_O0",
    "sass_total_instrs_O3", "sass_target_instrs_O3",
    "sass_gp_regs_O3", "sass_extra_regs_O3",
    "sass_sequence_O3", "sass_core_instrs_O3", "sass_core_sequence_O3",
    "core_filter_notes_O3",
    "audited_sass_instrs_O0", "audited_sass_sequence_O0",
    "audit_status", "audit_verdict", "audit_notes",
    "raw_verdict", "cleaned_verdict", "verdict", "notes",
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
                # The report is the canonical per-PTX evidence; never truncate
                # long tcgen05/TMA statements.
                "instruction": r.instruction,
                "ptx_reg_count": r.ptx_reg_count,
                "ptx_setup_count": r.ptx_setup_count,
                "sass_total_instrs_O0": r.sass_total_instrs_O0,
                "sass_target_instrs_O0": r.sass_target_instrs_O0,
                "sass_gp_regs_O0": r.sass_gp_regs_O0,
                "sass_extra_regs_O0": r.sass_extra_regs_O0,
                "sass_sequence_O0": r.sass_sequence_O0,
                "sass_core_instrs_O0": r.sass_core_instrs_O0,
                "sass_core_sequence_O0": r.sass_core_sequence_O0,
                "core_filter_notes_O0": r.core_filter_notes_O0,
                "sass_total_instrs_O3": r.sass_total_instrs_O3,
                "sass_target_instrs_O3": r.sass_target_instrs_O3,
                "sass_gp_regs_O3": r.sass_gp_regs_O3,
                "sass_extra_regs_O3": r.sass_extra_regs_O3,
                "sass_sequence_O3": r.sass_sequence_O3,
                "sass_core_instrs_O3": r.sass_core_instrs_O3,
                "sass_core_sequence_O3": r.sass_core_sequence_O3,
                "core_filter_notes_O3": r.core_filter_notes_O3,
                "audited_sass_instrs_O0": r.audited_sass_instrs_O0,
                "audited_sass_sequence_O0": r.audited_sass_sequence_O0,
                "audit_status": r.audit_status,
                "audit_verdict": r.audit_verdict,
                "audit_notes": r.audit_notes,
                "raw_verdict": r.raw_verdict,
                "cleaned_verdict": r.cleaned_verdict,
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
    expand_cases = [r for r in results if r.verdict == "1:N"]
    review_cases = [r for r in results if r.verdict == "NEEDS_REVIEW"]
    fail_cases = [r for r in results if r.verdict == "COMPILE_FAIL"]
    unsupported_cases = [
        r for r in results if r.verdict == "UNSUPPORTED_BY_PTX_ISA"
    ]

    if expand_cases:
        print("  EXPAND cases (require attention):")
        for r in expand_cases:
            effective_count = (
                r.audited_sass_instrs_O0
                if r.audit_status == "VERIFIED"
                else r.sass_core_instrs_O0
            )
            print(f"    [{r.batch}] {r.case_id} {r.mnemonic}: "
                  f"O0 audited={effective_count} instrs "
                  f"(cleaned={r.sass_core_instrs_O0}, "
                  f"raw={r.sass_target_instrs_O0}), "
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

    if unsupported_cases:
        print("\n  UNSUPPORTED_BY_PTX_ISA negative-test cases:")
        for r in unsupported_cases:
            print(f"    [{r.batch}] {r.case_id} {r.mnemonic}: {r.notes.rstrip('; ')}")

    print("\n" + "=" * 60)

    # 最终结论建议
    one_to_one = sum(1 for r in results if r.verdict in ("1:1", "1:1_FORMAT"))
    total_valid = sum(
        1 for r in results
        if r.verdict not in ("COMPILE_FAIL", "UNSUPPORTED_BY_PTX_ISA")
    )
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
            "1:N": "[!!]",
            "ELIMINATED": "[--]",
            "NO_CORE_SASS": "[0C]",
            "NEEDS_REVIEW": "[??]",
            "COMPILE_FAIL": "[XX]",
            "UNSUPPORTED_BY_PTX_ISA": "[NA]",
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

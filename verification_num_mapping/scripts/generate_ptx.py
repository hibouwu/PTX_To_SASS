#!/usr/bin/env python3
"""
PTX→SASS 1:1 映射验证 - PTX 测试用例批量生成脚本

为 Blackwell (sm_100) 架构下的每条目标 PTX 指令生成最小化 kernel,
用于验证 PTX→SASS 是否为 1:1 映射且不引入临时 GP 寄存器.
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass


BASE_DIR = Path(__file__).resolve().parent.parent / "ptx_sources"

HEADER = """\
.version 8.7
.target sm_100a
.address_size 64
"""

TARGET_MARKER = "// === target instruction"
END_TARGET_MARKER = "// === end target instruction ==="
SINK_DECLARATION = ".global .align 16 .b8 __ptx_sink[256];"


@dataclass
class PTXTestCase:
    batch: str       # 子目录名
    case_id: str     # 如 T01, M01, I01
    mnemonic: str    # 文件名用简短助记符
    description: str # 注释
    body: str        # kernel 完整体


def _declared_register_types(body: str) -> dict[str, str]:
    """Return a mapping from PTX register names to their declared types."""
    result = {}
    for match in re.finditer(r"\.reg\s+\.(\w+)\s+([^;]+);", body):
        ptx_type, declaration = match.groups()
        array_spans = []
        for array_match in re.finditer(r"%(\w+)<(\d+)>", declaration):
            base, count = array_match.groups()
            result.update({f"%{base}{index}": ptx_type for index in range(int(count))})
            array_spans.append(array_match.span())

        declaration_without_arrays = declaration
        for start, end in reversed(array_spans):
            declaration_without_arrays = (
                declaration_without_arrays[:start] + declaration_without_arrays[end:]
            )
        for register in re.findall(r"%[A-Za-z_$][\w$]*", declaration_without_arrays):
            result[register] = ptx_type
    return result


def _first_operand(operands: str) -> str:
    """Extract the first PTX operand while respecting vector/bracket nesting."""
    depth = 0
    for index, char in enumerate(operands):
        if char in "{[(":
            depth += 1
        elif char in "}])":
            depth -= 1
        elif char == "," and depth == 0:
            return operands[:index].strip()
    return operands.strip().rstrip(";")


def make_target_observable(body: str) -> str:
    """Add output sinks so ptxas cannot remove a side-effect-free target at -O0."""
    lines = body.splitlines()
    marker_index = next(
        (index for index, line in enumerate(lines) if TARGET_MARKER in line), None
    )
    if marker_index is None:
        entry_index = next(
            (index for index, line in enumerate(lines) if ".entry " in line), None
        )
        if entry_index is None:
            raise ValueError("PTX case is missing both an entry and a target marker")
        body_index = next(
            (index for index in range(entry_index, len(lines)) if "{" in lines[index]),
            None,
        )
        if body_index is None:
            raise ValueError("PTX entry is missing its body")
        target_index = next(
            (
                index
                for index in range(body_index + 1, len(lines))
                if lines[index].strip()
            ),
            None,
        )
        if target_index is None:
            raise ValueError("PTX entry body is empty")
        lines.insert(target_index, "    // === target instruction ===")
        marker_index = target_index

    target_start = marker_index + 1
    while target_start < len(lines) and not lines[target_start].strip():
        target_start += 1

    target_end = target_start
    while target_end < len(lines):
        stripped = lines[target_end].strip()
        if not stripped or stripped == "}" or stripped.endswith(":"):
            break
        if stripped == "ret;" and target_end > target_start:
            break
        target_end += 1

    register_types = _declared_register_types(body)
    destinations = []
    for line in lines[target_start:target_end]:
        instruction = re.sub(r"^@!?%\w+\s+", "", line.strip())
        parts = instruction.split(None, 1)
        if len(parts) != 2:
            continue
        first_operand = _first_operand(parts[1])
        if first_operand.startswith("["):
            continue
        for register in re.findall(r"%[A-Za-z_$][\w$]*", first_operand):
            if register in register_types and register not in destinations:
                destinations.append(register)

    sink_lines = ["    " + END_TARGET_MARKER, "    .loc 1 200 0"]
    sink_offset = 0
    for register in destinations:
        ptx_type = register_types[register]
        if ptx_type == "pred":
            sink_lines.extend([
                f"    @{register} st.global.u32 [__ptx_sink+{sink_offset}], 1;",
                f"    @!{register} st.global.u32 [__ptx_sink+{sink_offset}], 0;",
            ])
            sink_offset += 4
            continue

        width_match = re.search(r"(16|32|64)$", ptx_type)
        if not width_match:
            continue
        width = int(width_match.group(1))
        alignment = width // 8
        sink_offset = (sink_offset + alignment - 1) // alignment * alignment
        sink_lines.append(
            f"    st.global.b{width} [__ptx_sink+{sink_offset}], {register};"
        )
        sink_offset += alignment

    sink_lines.append("    .loc 1 300 0")
    lines[target_end:target_end] = sink_lines
    lines.insert(marker_index, "    .loc 1 10 0")
    lines.insert(marker_index + 2, "    .loc 1 100 0")
    observable_body = "\n".join(lines) + "\n"
    module_declarations = '.file 1 "ptx_mapping_case.ptx"\n'
    if destinations:
        module_declarations += SINK_DECLARATION + "\n"
    observable_body = observable_body.replace(
        ".address_size 64\n",
        f".address_size 64\n{module_declarations}",
        1,
    )
    return observable_body


def write_case(case: PTXTestCase):
    """将测试用例写入对应 PTX 文件."""
    out_dir = BASE_DIR / case.batch
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{case.case_id}_{case.mnemonic}.ptx"
    filepath = out_dir / filename
    try:
        body = make_target_observable(case.body)
    except ValueError as error:
        raise ValueError(f"{case.batch}/{case.case_id}: {error}") from error
    filepath.write_text(body, encoding="utf-8")
    return filepath


# ===========================================================================
# 第一批: tcgen05 指令族
# ===========================================================================

def gen_tcgen05_cases() -> list[PTXTestCase]:
    cases = []

    # T01: tcgen05.mma cta_group::1 standard (tf32)
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T01", mnemonic="mma_cg1_tf32",
        description="tcgen05.mma.cta_group::1.kind::tf32 standard",
        body=HEADER + """
// T01: tcgen05.mma.cta_group::1.kind::tf32 (standard)
// Requires allocated TMEM and valid SMEM descriptors.
.visible .entry test_tcgen05_mma_cg1_tf32(
    .param .u32 p_taddr,
    .param .u64 p_smem_desc_a,
    .param .u64 p_smem_desc_b,
    .param .u32 p_idesc
) {
    .reg .b32 %taddr;
    .reg .b64 %desc_a, %desc_b;
    .reg .b32 %idesc;
    .reg .b32 %mask<4>;
    .reg .pred %enable;

    ld.param.b32 %taddr, [p_taddr];
    ld.param.b64 %desc_a, [p_smem_desc_a];
    ld.param.b64 %desc_b, [p_smem_desc_b];
    ld.param.b32 %idesc, [p_idesc];
    mov.u32 %mask0, 0;
    mov.u32 %mask1, 0;
    mov.u32 %mask2, 0;
    mov.u32 %mask3, 0;
    setp.ne.u32 %enable, %idesc, 0;

    // === target instruction ===
    tcgen05.mma.cta_group::1.kind::tf32 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;

    ret;
}
"""))

    # T02: tcgen05.mma cta_group::2
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T02", mnemonic="mma_cg2_tf32",
        description="tcgen05.mma.cta_group::2.kind::tf32",
        body=HEADER + """
// T02: tcgen05.mma.cta_group::2.kind::tf32
.visible .entry test_tcgen05_mma_cg2_tf32(
    .param .u32 p_taddr,
    .param .u64 p_smem_desc_a,
    .param .u64 p_smem_desc_b,
    .param .u32 p_idesc
) {
    .reg .b32 %taddr;
    .reg .b64 %desc_a, %desc_b;
    .reg .b32 %idesc;
    .reg .b32 %mask<8>;
    .reg .pred %enable;

    ld.param.b32 %taddr, [p_taddr];
    ld.param.b64 %desc_a, [p_smem_desc_a];
    ld.param.b64 %desc_b, [p_smem_desc_b];
    ld.param.b32 %idesc, [p_idesc];
    mov.u32 %mask0, 0;
    mov.u32 %mask1, 0;
    mov.u32 %mask2, 0;
    mov.u32 %mask3, 0;
    mov.u32 %mask4, 0;
    mov.u32 %mask5, 0;
    mov.u32 %mask6, 0;
    mov.u32 %mask7, 0;
    setp.ne.u32 %enable, %idesc, 0;

    // === target instruction ===
    tcgen05.mma.cta_group::2.kind::tf32 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3, %mask4, %mask5, %mask6, %mask7}, %enable;

    ret;
}
"""))

    # T03: tcgen05.mma sparse
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T03", mnemonic="mma_cg1_tf32_sp",
        description="tcgen05.mma.cta_group::1.kind::tf32.sparse",
        body=HEADER + """
// T03: tcgen05.mma.cta_group::1.kind::tf32.sparse
.visible .entry test_tcgen05_mma_cg1_tf32_sparse(
    .param .u32 p_taddr,
    .param .u64 p_smem_desc_a,
    .param .u64 p_smem_desc_b,
    .param .u32 p_idesc,
    .param .u32 p_meta_addr
) {
    .reg .b32 %taddr, %idesc, %meta;
    .reg .b64 %desc_a, %desc_b;
    .reg .b32 %mask<4>;
    .reg .pred %enable;

    ld.param.b32 %taddr, [p_taddr];
    ld.param.b64 %desc_a, [p_smem_desc_a];
    ld.param.b64 %desc_b, [p_smem_desc_b];
    ld.param.b32 %idesc, [p_idesc];
    ld.param.b32 %meta, [p_meta_addr];
    mov.u32 %mask0, 0;
    mov.u32 %mask1, 0;
    mov.u32 %mask2, 0;
    mov.u32 %mask3, 0;
    setp.ne.u32 %enable, %idesc, 0;

    // === target instruction ===
    tcgen05.mma.sp.cta_group::1.kind::tf32 [%taddr], %desc_a, %desc_b, [%meta], %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;

    ret;
}
"""))

    # T04: tcgen05.cp
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T04", mnemonic="cp_cg1",
        description="tcgen05.cp.cta_group::1.128x256b",
        body=HEADER + """
// T04: tcgen05.cp.cta_group::1.128x256b
.visible .entry test_tcgen05_cp(
    .param .u32 p_taddr,
    .param .u64 p_smem_desc
) {
    .reg .u32 %taddr;
    .reg .u64 %desc;

    ld.param.u32 %taddr, [p_taddr];
    ld.param.u64 %desc, [p_smem_desc];

    // === target instruction ===
    tcgen05.cp.cta_group::1.128x256b [%taddr], %desc;

    ret;
}
"""))

    # T05: tcgen05.ld 16x64b x1
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T05", mnemonic="ld_16x64b_x1",
        description="tcgen05.ld.sync.aligned.16x64b.x1.b32",
        body=HEADER + """
// T05: tcgen05.ld.sync.aligned.16x64b.x1.b32
.visible .entry test_tcgen05_ld_16x64b_x1(
    .param .u32 p_taddr
) {
    .reg .u32 %taddr;
    .reg .b32 %dst<1>;

    ld.param.u32 %taddr, [p_taddr];

    // === target instruction ===
    tcgen05.ld.sync.aligned.16x64b.x1.b32 {%dst0}, [%taddr];

    ret;
}
"""))

    # T06: tcgen05.ld 16x128b x4
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T06", mnemonic="ld_16x128b_x4",
        description="tcgen05.ld.sync.aligned.16x128b.x4.b32",
        body=HEADER + """
// T06: tcgen05.ld.sync.aligned.16x128b.x4.b32
.visible .entry test_tcgen05_ld_16x128b_x4(
    .param .u32 p_taddr
) {
    .reg .u32 %taddr;
    .reg .b32 %dst<8>;

    ld.param.u32 %taddr, [p_taddr];

    // === target instruction ===
    tcgen05.ld.sync.aligned.16x128b.x4.b32 {%dst0, %dst1, %dst2, %dst3, %dst4, %dst5, %dst6, %dst7}, [%taddr];

    ret;
}
"""))

    # T07: tcgen05.st
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T07", mnemonic="st",
        description="tcgen05.st.sync.aligned",
        body=HEADER + """
// T07: tcgen05.st.sync.aligned
.visible .entry test_tcgen05_st(
    .param .u32 p_taddr
) {
    .reg .u32 %taddr;
    .reg .b32 %src<1>;

    ld.param.u32 %taddr, [p_taddr];
    mov.b32 %src0, 0;

    // === target instruction ===
    tcgen05.st.sync.aligned.16x64b.x1.b32 [%taddr], {%src0};

    ret;
}
"""))

    # T08: tcgen05.alloc
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T08", mnemonic="alloc_cg1",
        description="tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32",
        body=HEADER + """
// T08: tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32
.shared .align 4 .u32 smem_result;

.visible .entry test_tcgen05_alloc(
    .param .u32 p_ncols
) {
    .reg .u32 %ncols;

    ld.param.u32 %ncols, [p_ncols];

    // === target instruction ===
    tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 [smem_result], %ncols;

    ret;
}
"""))

    # T09: tcgen05.dealloc
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T09", mnemonic="dealloc_cg1",
        description="tcgen05.dealloc.cta_group::1.sync.aligned.b32",
        body=HEADER + """
// T09: tcgen05.dealloc.cta_group::1.sync.aligned.b32
.visible .entry test_tcgen05_dealloc(
    .param .u32 p_taddr,
    .param .u32 p_ncols
) {
    .reg .u32 %taddr, %ncols;

    ld.param.u32 %taddr, [p_taddr];
    ld.param.u32 %ncols, [p_ncols];

    // === target instruction ===
    tcgen05.dealloc.cta_group::1.sync.aligned.b32 %taddr, %ncols;

    ret;
}
"""))

    # T10: tcgen05.commit
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T10", mnemonic="commit_cg1",
        description="tcgen05.commit.cta_group::1.mbarrier::arrive::one",
        body=HEADER + """
// T10: tcgen05.commit.cta_group::1.mbarrier::arrive::one
.shared .align 8 .u64 smem_mbar;

.visible .entry test_tcgen05_commit() {
    // === target instruction ===
    tcgen05.commit.cta_group::1.mbarrier::arrive::one.shared::cluster.b64 [smem_mbar];

    ret;
}
"""))

    # T11: tcgen05.fence
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T11", mnemonic="fence",
        description="tcgen05.fence::after_thread_sync",
        body=HEADER + """
// T11: tcgen05.fence::after_thread_sync
.visible .entry test_tcgen05_fence() {
    // === target instruction ===
    tcgen05.fence::after_thread_sync;

    ret;
}
"""))

    # T12: tcgen05.mma kind::f16 (FP16 MMA, inference primary)
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T12", mnemonic="mma_cg1_f16",
        description="tcgen05.mma.cta_group::1.kind::f16 (FP16, inference primary)",
        body=HEADER + """
// T12: tcgen05.mma.cta_group::1.kind::f16
.visible .entry test_tcgen05_mma_cg1_f16(
    .param .u32 p_taddr,
    .param .u64 p_smem_desc_a,
    .param .u64 p_smem_desc_b,
    .param .u32 p_idesc
) {
    .reg .b32 %taddr;
    .reg .b64 %desc_a, %desc_b;
    .reg .b32 %idesc;
    .reg .b32 %mask<4>;
    .reg .pred %enable;

    ld.param.b32 %taddr, [p_taddr];
    ld.param.b64 %desc_a, [p_smem_desc_a];
    ld.param.b64 %desc_b, [p_smem_desc_b];
    ld.param.b32 %idesc, [p_idesc];
    mov.u32 %mask0, 0;
    mov.u32 %mask1, 0;
    mov.u32 %mask2, 0;
    mov.u32 %mask3, 0;
    setp.ne.u32 %enable, %idesc, 0;

    // === target instruction ===
    tcgen05.mma.cta_group::1.kind::f16 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;

    ret;
}
"""))

    # T13: BF16 uses kind::f16; operand formats are encoded by the instruction descriptor.
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T13", mnemonic="mma_cg1_bf16",
        description="tcgen05.mma.cta_group::1.kind::f16 (BF16 via descriptor)",
        body=HEADER + """
// T13: tcgen05.mma.cta_group::1.kind::f16 (BF16 descriptor)
.visible .entry test_tcgen05_mma_cg1_bf16(
    .param .u32 p_taddr,
    .param .u64 p_smem_desc_a,
    .param .u64 p_smem_desc_b,
    .param .u32 p_idesc
) {
    .reg .b32 %taddr;
    .reg .b64 %desc_a, %desc_b;
    .reg .b32 %idesc;
    .reg .b32 %mask<4>;
    .reg .pred %enable;

    ld.param.b32 %taddr, [p_taddr];
    ld.param.b64 %desc_a, [p_smem_desc_a];
    ld.param.b64 %desc_b, [p_smem_desc_b];
    ld.param.b32 %idesc, [p_idesc];
    mov.u32 %mask0, 0;
    mov.u32 %mask1, 0;
    mov.u32 %mask2, 0;
    mov.u32 %mask3, 0;
    setp.ne.u32 %enable, %idesc, 0;

    // === target instruction ===
    tcgen05.mma.cta_group::1.kind::f16 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;

    ret;
}
"""))

    # T14: tcgen05.mma kind::f8f6f4 (FP8/FP6/FP4 MMA, quantized inference)
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T14", mnemonic="mma_cg1_f8f6f4",
        description="tcgen05.mma.cta_group::1.kind::f8f6f4 (FP8/FP6/FP4, quantized)",
        body=HEADER + """
// T14: tcgen05.mma.cta_group::1.kind::f8f6f4
.visible .entry test_tcgen05_mma_cg1_f8f6f4(
    .param .u32 p_taddr,
    .param .u64 p_smem_desc_a,
    .param .u64 p_smem_desc_b,
    .param .u32 p_idesc
) {
    .reg .b32 %taddr;
    .reg .b64 %desc_a, %desc_b;
    .reg .b32 %idesc;
    .reg .b32 %mask<4>;
    .reg .pred %enable;

    ld.param.b32 %taddr, [p_taddr];
    ld.param.b64 %desc_a, [p_smem_desc_a];
    ld.param.b64 %desc_b, [p_smem_desc_b];
    ld.param.b32 %idesc, [p_idesc];
    mov.u32 %mask0, 0;
    mov.u32 %mask1, 0;
    mov.u32 %mask2, 0;
    mov.u32 %mask3, 0;
    setp.ne.u32 %enable, %idesc, 0;

    // === target instruction ===
    tcgen05.mma.cta_group::1.kind::f8f6f4 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;

    ret;
}
"""))

    # T15: tcgen05.mma kind::i8 (INT8 MMA)
    cases.append(PTXTestCase(
        batch="01_tcgen05", case_id="T15", mnemonic="mma_cg1_i8",
        description="tcgen05.mma.cta_group::1.kind::i8 (INT8, quantized)",
        body=HEADER + """
// T15: tcgen05.mma.cta_group::1.kind::i8
.visible .entry test_tcgen05_mma_cg1_i8(
    .param .u32 p_taddr,
    .param .u64 p_smem_desc_a,
    .param .u64 p_smem_desc_b,
    .param .u32 p_idesc
) {
    .reg .b32 %taddr;
    .reg .b64 %desc_a, %desc_b;
    .reg .b32 %idesc;
    .reg .b32 %mask<4>;
    .reg .pred %enable;

    ld.param.b32 %taddr, [p_taddr];
    ld.param.b64 %desc_a, [p_smem_desc_a];
    ld.param.b64 %desc_b, [p_smem_desc_b];
    ld.param.b32 %idesc, [p_idesc];
    mov.u32 %mask0, 0;
    mov.u32 %mask1, 0;
    mov.u32 %mask2, 0;
    mov.u32 %mask3, 0;
    setp.ne.u32 %enable, %idesc, 0;

    // === target instruction ===
    tcgen05.mma.cta_group::1.kind::i8 [%taddr], %desc_a, %desc_b, %idesc, {%mask0, %mask1, %mask2, %mask3}, %enable;

    ret;
}
"""))

    return cases


# ===========================================================================
# 第二批: TMA 指令族
# ===========================================================================

def gen_tma_cases() -> list[PTXTestCase]:
    cases = []

    # M01: TMA 2D load
    cases.append(PTXTestCase(
        batch="02_tma", case_id="M01", mnemonic="load_2d",
        description="cp.async.bulk.tensor.2d load",
        body=HEADER + """
// M01: cp.async.bulk.tensor.2d.shared::cta.global.mbarrier::complete_tx::bytes
.shared .align 128 .u8 smem_buf[1024];
.shared .align 8 .u64 smem_mbar;

.visible .entry test_tma_load_2d(
    .param .u64 p_desc
) {
    .reg .u64 %desc;
    .reg .u32 %c0, %c1;

    ld.param.u64 %desc, [p_desc];
    mov.u32 %c0, 0;
    mov.u32 %c1, 0;

    // === target instruction ===
    cp.async.bulk.tensor.2d.shared::cta.global.mbarrier::complete_tx::bytes [smem_buf], [%desc, {%c0, %c1}], [smem_mbar];

    ret;
}
"""))

    # M02: TMA 3D load
    cases.append(PTXTestCase(
        batch="02_tma", case_id="M02", mnemonic="load_3d",
        description="cp.async.bulk.tensor.3d load",
        body=HEADER + """
// M02: cp.async.bulk.tensor.3d.shared::cta.global.mbarrier::complete_tx::bytes
.shared .align 128 .u8 smem_buf[1024];
.shared .align 8 .u64 smem_mbar;

.visible .entry test_tma_load_3d(
    .param .u64 p_desc
) {
    .reg .u64 %desc;
    .reg .u32 %c0, %c1, %c2;

    ld.param.u64 %desc, [p_desc];
    mov.u32 %c0, 0;
    mov.u32 %c1, 0;
    mov.u32 %c2, 0;

    // === target instruction ===
    cp.async.bulk.tensor.3d.shared::cta.global.mbarrier::complete_tx::bytes [smem_buf], [%desc, {%c0, %c1, %c2}], [smem_mbar];

    ret;
}
"""))

    # M03: TMA multicast load
    cases.append(PTXTestCase(
        batch="02_tma", case_id="M03", mnemonic="load_2d_mc",
        description="cp.async.bulk.tensor.2d multicast",
        body=HEADER + """
// M03: cp.async.bulk.tensor.2d multicast
.shared .align 128 .u8 smem_buf[1024];
.shared .align 8 .u64 smem_mbar;

.visible .entry test_tma_load_2d_multicast(
    .param .u64 p_desc,
    .param .u16 p_mask
) {
    .reg .u64 %desc;
    .reg .u32 %c0, %c1;
    .reg .u16 %mask;

    ld.param.u64 %desc, [p_desc];
    ld.param.u16 %mask, [p_mask];
    mov.u32 %c0, 0;
    mov.u32 %c1, 0;

    // === target instruction ===
    cp.async.bulk.tensor.2d.shared::cluster.global.mbarrier::complete_tx::bytes.multicast::cluster [smem_buf], [%desc, {%c0, %c1}], [smem_mbar], %mask;

    ret;
}
"""))

    # M04: TMA store
    cases.append(PTXTestCase(
        batch="02_tma", case_id="M04", mnemonic="store_2d",
        description="cp.async.bulk.tensor.2d store",
        body=HEADER + """
// M04: cp.async.bulk.tensor.2d.global.shared::cta.bulk_group (store)
.shared .align 128 .u8 smem_buf[1024];

.visible .entry test_tma_store_2d(
    .param .u64 p_desc
) {
    .reg .u64 %desc;
    .reg .u32 %c0, %c1;

    ld.param.u64 %desc, [p_desc];
    mov.u32 %c0, 0;
    mov.u32 %c1, 0;

    // === target instruction ===
    cp.async.bulk.tensor.2d.global.shared::cta.bulk_group [%desc, {%c0, %c1}], [smem_buf];

    ret;
}
"""))

    # M05: TMA reduce store
    cases.append(PTXTestCase(
        batch="02_tma", case_id="M05", mnemonic="reduce_add_2d",
        description="cp.reduce.async.bulk.tensor.2d add",
        body=HEADER + """
// M05: cp.reduce.async.bulk.tensor.2d.global.shared::cta.add.bulk_group
.shared .align 128 .u8 smem_buf[1024];

.visible .entry test_tma_reduce_add_2d(
    .param .u64 p_desc
) {
    .reg .u64 %desc;
    .reg .u32 %c0, %c1;

    ld.param.u64 %desc, [p_desc];
    mov.u32 %c0, 0;
    mov.u32 %c1, 0;

    // === target instruction ===
    cp.reduce.async.bulk.tensor.2d.global.shared::cta.add.bulk_group [%desc, {%c0, %c1}], [smem_buf];

    ret;
}
"""))

    # M06: TMA prefetch
    cases.append(PTXTestCase(
        batch="02_tma", case_id="M06", mnemonic="prefetch_2d",
        description="cp.async.bulk.prefetch.tensor.2d",
        body=HEADER + """
// M06: cp.async.bulk.prefetch.tensor.2d
.visible .entry test_tma_prefetch_2d(
    .param .u64 p_desc
) {
    .reg .u64 %desc;
    .reg .u32 %c0, %c1;

    ld.param.u64 %desc, [p_desc];
    mov.u32 %c0, 0;
    mov.u32 %c1, 0;

    // === target instruction ===
    cp.async.bulk.prefetch.tensor.2d.L2.global [%desc, {%c0, %c1}];

    ret;
}
"""))

    # M07: commit_group
    cases.append(PTXTestCase(
        batch="02_tma", case_id="M07", mnemonic="commit_group",
        description="cp.async.bulk.commit_group",
        body=HEADER + """
// M07: cp.async.bulk.commit_group
.visible .entry test_commit_group() {
    // === target instruction ===
    cp.async.bulk.commit_group;

    ret;
}
"""))

    # M08: cp.async.ca (non-bulk, classic async copy)
    cases.append(PTXTestCase(
        batch="02_tma", case_id="M08", mnemonic="cp_async_ca",
        description="cp.async.ca.shared.global (non-bulk classic)",
        body=HEADER + """
// M08: cp.async.ca.shared.global (pre-TMA async copy)
.shared .align 4 .u32 smem_data[256];

.visible .entry test_cp_async_ca(
    .param .u64 p_gaddr
) {
    .reg .u64 %gaddr;
    ld.param.u64 %gaddr, [p_gaddr];

    // === target instruction ===
    cp.async.ca.shared.global [smem_data], [%gaddr], 4;

    ret;
}
"""))

    # M09: cp.async.cg (commit group variant)
    cases.append(PTXTestCase(
        batch="02_tma", case_id="M09", mnemonic="cp_async_cg",
        description="cp.async.cg.shared.global (commit group)",
        body=HEADER + """
// M09: cp.async.cg.shared.global (commit group variant)
.shared .align 16 .u32 smem_data16[256];

.visible .entry test_cp_async_cg(
    .param .u64 p_gaddr
) {
    .reg .u64 %gaddr;
    ld.param.u64 %gaddr, [p_gaddr];

    // === target instruction ===
    cp.async.cg.shared.global [smem_data16], [%gaddr], 16;

    ret;
}
"""))

    # M10: cp.async.wait_group
    cases.append(PTXTestCase(
        batch="02_tma", case_id="M10", mnemonic="cp_async_wait",
        description="cp.async.wait_group 0",
        body=HEADER + """
// M10: cp.async.wait_group 0
.visible .entry test_cp_async_wait() {
    // === target instruction ===
    cp.async.wait_group 0;

    ret;
}
"""))

    return cases


# ===========================================================================
# 第三批: mbarrier 指令族
# ===========================================================================

def gen_mbarrier_cases() -> list[PTXTestCase]:
    cases = []

    smem_decl = ".shared .align 8 .u64 smem_mbar;\n"

    # B01: mbarrier.init
    cases.append(PTXTestCase(
        batch="03_mbarrier", case_id="B01", mnemonic="init",
        description="mbarrier.init.shared::cta.b64",
        body=HEADER + smem_decl + """
.visible .entry test_mbarrier_init(
    .param .u32 p_count
) {
    .reg .u32 %count;
    ld.param.u32 %count, [p_count];

    // === target instruction ===
    mbarrier.init.shared::cta.b64 [smem_mbar], %count;

    ret;
}
"""))

    # B02: mbarrier.arrive
    cases.append(PTXTestCase(
        batch="03_mbarrier", case_id="B02", mnemonic="arrive",
        description="mbarrier.arrive.shared::cta.b64",
        body=HEADER + smem_decl + """
.visible .entry test_mbarrier_arrive() {
    .reg .b64 %state;

    // === target instruction ===
    mbarrier.arrive.shared::cta.b64 %state, [smem_mbar];

    ret;
}
"""))

    # B03: mbarrier.arrive.expect_tx
    cases.append(PTXTestCase(
        batch="03_mbarrier", case_id="B03", mnemonic="arrive_expect_tx",
        description="mbarrier.arrive.expect_tx.shared::cta.b64",
        body=HEADER + smem_decl + """
.visible .entry test_mbarrier_arrive_expect_tx(
    .param .u32 p_tx
) {
    .reg .b64 %state;
    .reg .u32 %tx;
    ld.param.u32 %tx, [p_tx];

    // === target instruction ===
    mbarrier.arrive.expect_tx.shared::cta.b64 %state, [smem_mbar], %tx;

    ret;
}
"""))

    # B04: mbarrier.arrive.drop (noTx variant)
    cases.append(PTXTestCase(
        batch="03_mbarrier", case_id="B04", mnemonic="arrive_drop",
        description="mbarrier.arrive_drop.shared::cta.b64",
        body=HEADER + smem_decl + """
.visible .entry test_mbarrier_arrive_drop() {
    .reg .b64 %state;

    // === target instruction ===
    mbarrier.arrive_drop.shared::cta.b64 %state, [smem_mbar];

    ret;
}
"""))

    # B05: mbarrier.expect_tx
    cases.append(PTXTestCase(
        batch="03_mbarrier", case_id="B05", mnemonic="expect_tx",
        description="mbarrier.expect_tx.shared::cta.b64",
        body=HEADER + smem_decl + """
.visible .entry test_mbarrier_expect_tx(
    .param .u32 p_tx
) {
    .reg .u32 %tx;
    ld.param.u32 %tx, [p_tx];

    // === target instruction ===
    mbarrier.expect_tx.shared::cta.b64 [smem_mbar], %tx;

    ret;
}
"""))

    # B06: mbarrier.complete_tx (note: this is done via arrive in newer PTX)
    cases.append(PTXTestCase(
        batch="03_mbarrier", case_id="B06", mnemonic="complete_tx",
        description="mbarrier.complete_tx.relaxed.cta.shared::cta.b64",
        body=HEADER + smem_decl + """
.visible .entry test_mbarrier_complete_tx(
    .param .u32 p_tx
) {
    .reg .u32 %tx;
    ld.param.u32 %tx, [p_tx];

    // === target instruction ===
    mbarrier.complete_tx.relaxed.cta.shared::cta.b64 [smem_mbar], %tx;

    ret;
}
"""))

    # B07: mbarrier.try_wait (NOTE: may generate loop)
    cases.append(PTXTestCase(
        batch="03_mbarrier", case_id="B07", mnemonic="try_wait",
        description="mbarrier.try_wait.parity - NOTE: may generate SASS loop",
        body=HEADER + smem_decl + """
.visible .entry test_mbarrier_try_wait() {
    .reg .pred %done;

    // === target instruction (blocking semantics may lower to a loop) ===
    mbarrier.try_wait.parity.shared::cta.b64 %done, [smem_mbar], 0;

    ret;
}
"""))

    # B08: mbarrier.test_wait
    cases.append(PTXTestCase(
        batch="03_mbarrier", case_id="B08", mnemonic="test_wait",
        description="mbarrier.test_wait.parity.shared::cta.b64",
        body=HEADER + smem_decl + """
.visible .entry test_mbarrier_test_wait() {
    .reg .pred %result;

    // === target instruction ===
    mbarrier.test_wait.parity.shared::cta.b64 %result, [smem_mbar], 0;

    ret;
}
"""))

    # B09: mbarrier.inval
    cases.append(PTXTestCase(
        batch="03_mbarrier", case_id="B09", mnemonic="inval",
        description="mbarrier.inval.shared::cta.b64",
        body=HEADER + smem_decl + """
.visible .entry test_mbarrier_inval() {
    // === target instruction ===
    mbarrier.inval.shared::cta.b64 [smem_mbar];

    ret;
}
"""))

    return cases


# ===========================================================================
# 第四批: Fence / Barrier 同步
# ===========================================================================

def gen_fence_cases() -> list[PTXTestCase]:
    cases = []

    # F01
    cases.append(PTXTestCase(
        batch="04_fence", case_id="F01", mnemonic="proxy_async_cta",
        description="fence.proxy.async.shared::cta",
        body=HEADER + """
.visible .entry test_fence_proxy_async_cta() {
    fence.proxy.async.shared::cta;
    ret;
}
"""))

    # F02
    cases.append(PTXTestCase(
        batch="04_fence", case_id="F02", mnemonic="proxy_async_cluster",
        description="fence.proxy.async.shared::cluster",
        body=HEADER + """
.visible .entry test_fence_proxy_async_cluster() {
    fence.proxy.async.shared::cluster;
    ret;
}
"""))

    # F03
    cases.append(PTXTestCase(
        batch="04_fence", case_id="F03", mnemonic="proxy_async_generic",
        description="fence.proxy.async",
        body=HEADER + """
.visible .entry test_fence_proxy_async_generic() {
    fence.proxy.async;
    ret;
}
"""))

    # F04
    cases.append(PTXTestCase(
        batch="04_fence", case_id="F04", mnemonic="proxy_tensormap",
        description="fence.proxy.tensormap::generic.release.cta",
        body=HEADER + """
.visible .entry test_fence_proxy_tensormap() {
    fence.proxy.tensormap::generic.release.cta;
    ret;
}
"""))

    # F05
    cases.append(PTXTestCase(
        batch="04_fence", case_id="F05", mnemonic="mbarrier_init_fence",
        description="fence.mbarrier_init.release.cluster",
        body=HEADER + """
.visible .entry test_fence_mbarrier_init() {
    fence.mbarrier_init.release.cluster;
    ret;
}
"""))

    # F06
    cases.append(PTXTestCase(
        batch="04_fence", case_id="F06", mnemonic="barrier_cluster_arrive",
        description="barrier.cluster.arrive",
        body=HEADER + """
.visible .entry test_barrier_cluster_arrive() {
    barrier.cluster.arrive;
    ret;
}
"""))

    # F07
    cases.append(PTXTestCase(
        batch="04_fence", case_id="F07", mnemonic="barrier_cluster_wait",
        description="barrier.cluster.wait",
        body=HEADER + """
.visible .entry test_barrier_cluster_wait() {
    barrier.cluster.wait;
    ret;
}
"""))

    # F08
    cases.append(PTXTestCase(
        batch="04_fence", case_id="F08", mnemonic="fence_acq_rel_cta",
        description="fence.acq_rel.cta",
        body=HEADER + """
.visible .entry test_fence_acq_rel_cta() {
    fence.acq_rel.cta;
    ret;
}
"""))

    # F09
    cases.append(PTXTestCase(
        batch="04_fence", case_id="F09", mnemonic="bar_arrive",
        description="bar.arrive (named barrier)",
        body=HEADER + """
.visible .entry test_bar_arrive() {
    bar.arrive 0, 32;
    ret;
}
"""))

    # F10
    cases.append(PTXTestCase(
        batch="04_fence", case_id="F10", mnemonic="bar_sync",
        description="bar.sync (named barrier)",
        body=HEADER + """
.visible .entry test_bar_sync() {
    bar.sync 0, 32;
    ret;
}
"""))

    return cases


# ===========================================================================
# 第五批: CUDA Core 整数/标量运算
# ===========================================================================

def gen_int_cases() -> list[PTXTestCase]:
    cases = []

    def simple_int_kernel(case_id, mnemonic, desc, instr, regs=".reg .s32 %r0, %r1, %r2;",
                          setup="mov.s32 %r0, 42;\nmov.s32 %r1, 7;"):
        return PTXTestCase(
            batch="05_cuda_core_int", case_id=case_id, mnemonic=mnemonic,
            description=desc,
            body=HEADER + f"""
// {case_id}: {desc}
.visible .entry test_{mnemonic}() {{
    {regs}

    {setup}

    // === target instruction ===
    {instr}

    ret;
}}
""")

    # I01: add.s32
    cases.append(simple_int_kernel("I01", "add_s32", "add.s32",
                                   "add.s32 %r2, %r0, %r1;"))
    # I02: add.s64
    cases.append(simple_int_kernel("I02", "add_s64", "add.s64",
                                   "add.s64 %rd2, %rd0, %rd1;",
                                   regs=".reg .s64 %rd0, %rd1, %rd2;",
                                   setup="mov.s64 %rd0, 42;\nmov.s64 %rd1, 7;"))
    # I03: sub.s64
    cases.append(simple_int_kernel("I03", "sub_s64", "sub.s64",
                                   "sub.s64 %rd2, %rd0, %rd1;",
                                   regs=".reg .s64 %rd0, %rd1, %rd2;",
                                   setup="mov.s64 %rd0, 42;\nmov.s64 %rd1, 7;"))
    # I04: mul.lo.s32
    cases.append(simple_int_kernel("I04", "mul_lo_s32", "mul.lo.s32",
                                   "mul.lo.s32 %r2, %r0, %r1;"))
    # I05: mul.hi.s32
    cases.append(simple_int_kernel("I05", "mul_hi_s32", "mul.hi.s32",
                                   "mul.hi.s32 %r2, %r0, %r1;"))
    # I06: mul.wide.s32
    cases.append(simple_int_kernel("I06", "mul_wide_s32", "mul.wide.s32 (32x32->64)",
                                   "mul.wide.s32 %rd0, %r0, %r1;",
                                   regs=".reg .s32 %r0, %r1;\n    .reg .s64 %rd0;",
                                   setup="mov.s32 %r0, 42;\nmov.s32 %r1, 7;"))
    # I07: mul.lo.s64
    cases.append(simple_int_kernel("I07", "mul_lo_s64", "mul.lo.s64",
                                   "mul.lo.s64 %rd2, %rd0, %rd1;",
                                   regs=".reg .s64 %rd0, %rd1, %rd2;",
                                   setup="mov.s64 %rd0, 42;\nmov.s64 %rd1, 7;"))
    # I08: mad.lo.s32
    cases.append(simple_int_kernel("I08", "mad_lo_s32", "mad.lo.s32",
                                   "mad.lo.s32 %r2, %r0, %r1, %r2;",
                                   setup="mov.s32 %r0, 42;\nmov.s32 %r1, 7;\nmov.s32 %r2, 1;"))
    # I09: mad.wide.u32
    cases.append(simple_int_kernel("I09", "mad_wide_u32", "mad.wide.u32 (32x32+64->64)",
                                   "mad.wide.u32 %rd0, %r0, %r1, %rd0;",
                                   regs=".reg .u32 %r0, %r1;\n    .reg .u64 %rd0;",
                                   setup="mov.u32 %r0, 42;\nmov.u32 %r1, 7;\nmov.u64 %rd0, 100;"))
    # I10: div.s32 (HIGH RISK)
    cases.append(simple_int_kernel("I10", "div_s32", "div.s32 (HIGH RISK: no HW divider?)",
                                   "div.s32 %r2, %r0, %r1;"))
    # I11: div.u32 (HIGH RISK)
    cases.append(simple_int_kernel("I11", "div_u32", "div.u32 (HIGH RISK)",
                                   "div.u32 %r2, %r0, %r1;",
                                   regs=".reg .u32 %r0, %r1, %r2;",
                                   setup="mov.u32 %r0, 42;\nmov.u32 %r1, 7;"))
    # I12: rem.s32 (HIGH RISK)
    cases.append(simple_int_kernel("I12", "rem_s32", "rem.s32 (HIGH RISK)",
                                   "rem.s32 %r2, %r0, %r1;"))
    # I13: rem.u32 (HIGH RISK)
    cases.append(simple_int_kernel("I13", "rem_u32", "rem.u32 (HIGH RISK)",
                                   "rem.u32 %r2, %r0, %r1;",
                                   regs=".reg .u32 %r0, %r1, %r2;",
                                   setup="mov.u32 %r0, 42;\nmov.u32 %r1, 7;"))
    # I14: shl.b32
    cases.append(simple_int_kernel("I14", "shl_b32", "shl.b32",
                                   "shl.b32 %r2, %r0, 4;",
                                   regs=".reg .b32 %r0, %r2;",
                                   setup="mov.b32 %r0, 42;"))
    # I15: shl.b64
    cases.append(simple_int_kernel("I15", "shl_b64", "shl.b64",
                                   "shl.b64 %rd1, %rd0, 4;",
                                   regs=".reg .b64 %rd0, %rd1;",
                                   setup="mov.b64 %rd0, 42;"))
    # I16: shr.s64
    cases.append(simple_int_kernel("I16", "shr_s64", "shr.s64",
                                   "shr.s64 %rd1, %rd0, 4;",
                                   regs=".reg .s64 %rd0, %rd1;",
                                   setup="mov.s64 %rd0, 42;"))
    # Keep exactly one target PTX statement per case so source-line attribution
    # yields an unambiguous PTX -> SASS sequence.
    logic32_setup = "mov.b32 %r0, 0xFF00FF00;\nmov.b32 %r1, 0x0F0F0F0F;"
    for case_id, mnemonic, instruction in (
        ("I17A", "and_b32", "and.b32 %r2, %r0, %r1;"),
        ("I17B", "or_b32", "or.b32 %r2, %r0, %r1;"),
        ("I17C", "xor_b32", "xor.b32 %r2, %r0, %r1;"),
    ):
        cases.append(simple_int_kernel(
            case_id, mnemonic, instruction.removesuffix(";"), instruction,
            regs=".reg .b32 %r0, %r1, %r2;", setup=logic32_setup))

    logic64_setup = (
        "mov.b64 %rd0, 0xFF00FF00FF00FF00;\n"
        "mov.b64 %rd1, 0x0F0F0F0F0F0F0F0F;"
    )
    for case_id, mnemonic, instruction in (
        ("I18A", "and_b64", "and.b64 %rd2, %rd0, %rd1;"),
        ("I18B", "or_b64", "or.b64 %rd2, %rd0, %rd1;"),
    ):
        cases.append(simple_int_kernel(
            case_id, mnemonic, instruction.removesuffix(";"), instruction,
            regs=".reg .b64 %rd0, %rd1, %rd2;", setup=logic64_setup))

    compare_setup = "mov.s32 %r0, 42;\nmov.s32 %r1, 7;"
    for case_id, mnemonic, instruction, predicate in (
        ("I19A", "setp_eq_s32", "setp.eq.s32 %p0, %r0, %r1;", "%p0"),
        ("I19B", "setp_lt_s32", "setp.lt.s32 %p0, %r0, %r1;", "%p0"),
    ):
        cases.append(simple_int_kernel(
            case_id, mnemonic, instruction.removesuffix(";"), instruction,
            regs=f".reg .s32 %r0, %r1;\n    .reg .pred {predicate};",
            setup=compare_setup))

    cases.append(simple_int_kernel(
        "I20", "selp_b32", "selp.b32", "selp.b32 %r2, %r0, %r1, %p0;",
        regs=".reg .s32 %r0, %r1, %r2;\n    .reg .pred %p0;",
        setup=compare_setup + "\nsetp.eq.s32 %p0, %r0, %r1;"))

    cases.append(simple_int_kernel(
        "I21A", "mov_b32", "mov.b32 (data movement)", "mov.b32 %r1, %r0;",
        regs=".reg .b32 %r0, %r1;", setup="mov.b32 %r0, 42;"))
    cases.append(simple_int_kernel(
        "I21B", "mov_b64", "mov.b64 (data movement)", "mov.b64 %rd1, %rd0;",
        regs=".reg .b64 %rd0, %rd1;", setup="mov.b64 %rd0, 42;"))

    return cases


# ===========================================================================
# 第六批: CUDA Core 浮点运算
# ===========================================================================

def gen_fp_cases() -> list[PTXTestCase]:
    cases = []

    def fp_kernel(case_id, mnemonic, desc, instr, regs, setup):
        return PTXTestCase(
            batch="06_cuda_core_fp", case_id=case_id, mnemonic=mnemonic,
            description=desc,
            body=HEADER + f"""
// {case_id}: {desc}
.visible .entry test_{mnemonic}() {{
    {regs}

    {setup}

    // === target instruction ===
    {instr}

    ret;
}}
""")

    cases.append(fp_kernel("FP01", "add_f32", "add.f32",
        "add.f32 %f2, %f0, %f1;",
        ".reg .f32 %f0, %f1, %f2;",
        "mov.f32 %f0, 0f3F800000;\nmov.f32 %f1, 0f40000000;"))

    cases.append(fp_kernel("FP02", "mul_f32", "mul.f32",
        "mul.f32 %f2, %f0, %f1;",
        ".reg .f32 %f0, %f1, %f2;",
        "mov.f32 %f0, 0f3F800000;\nmov.f32 %f1, 0f40000000;"))

    cases.append(fp_kernel("FP03", "fma_rn_f32", "fma.rn.f32",
        "fma.rn.f32 %f2, %f0, %f1, %f2;",
        ".reg .f32 %f0, %f1, %f2;",
        "mov.f32 %f0, 0f3F800000;\nmov.f32 %f1, 0f40000000;\nmov.f32 %f2, 0f00000000;"))

    cases.append(fp_kernel("FP04", "add_f64", "add.f64",
        "add.f64 %fd2, %fd0, %fd1;",
        ".reg .f64 %fd0, %fd1, %fd2;",
        "mov.f64 %fd0, 0d3FF0000000000000;\nmov.f64 %fd1, 0d4000000000000000;"))

    cases.append(fp_kernel("FP05", "mul_f64", "mul.f64",
        "mul.f64 %fd2, %fd0, %fd1;",
        ".reg .f64 %fd0, %fd1, %fd2;",
        "mov.f64 %fd0, 0d3FF0000000000000;\nmov.f64 %fd1, 0d4000000000000000;"))

    cases.append(fp_kernel("FP06", "fma_rn_f64", "fma.rn.f64",
        "fma.rn.f64 %fd2, %fd0, %fd1, %fd2;",
        ".reg .f64 %fd0, %fd1, %fd2;",
        "mov.f64 %fd0, 0d3FF0000000000000;\nmov.f64 %fd1, 0d4000000000000000;\nmov.f64 %fd2, 0d0000000000000000;"))

    cases.append(fp_kernel("FP07A", "max_f32", "max.f32",
        "max.f32 %f2, %f0, %f1;",
        ".reg .f32 %f0, %f1, %f2;",
        "mov.f32 %f0, 0f3F800000;\nmov.f32 %f1, 0f40000000;"))

    cases.append(fp_kernel("FP07B", "min_f32", "min.f32",
        "min.f32 %f2, %f0, %f1;",
        ".reg .f32 %f0, %f1, %f2;",
        "mov.f32 %f0, 0f3F800000;\nmov.f32 %f1, 0f40000000;"))

    cases.append(fp_kernel("FP08A", "abs_f32", "abs.f32",
        "abs.f32 %f1, %f0;",
        ".reg .f32 %f0, %f1;",
        "mov.f32 %f0, 0fBF800000;"))

    cases.append(fp_kernel("FP08B", "neg_f32", "neg.f32",
        "neg.f32 %f1, %f0;",
        ".reg .f32 %f0, %f1;",
        "mov.f32 %f0, 0fBF800000;"))

    cases.append(fp_kernel("FP09", "ex2_f32", "ex2.approx.f32 (SFU)",
        "ex2.approx.f32 %f1, %f0;",
        ".reg .f32 %f0, %f1;",
        "mov.f32 %f0, 0f3F800000;"))

    cases.append(fp_kernel("FP10", "lg2_f32", "lg2.approx.f32 (SFU)",
        "lg2.approx.f32 %f1, %f0;",
        ".reg .f32 %f0, %f1;",
        "mov.f32 %f0, 0f40000000;"))

    cases.append(fp_kernel("FP11", "rcp_approx_f32", "rcp.approx.f32 (SFU)",
        "rcp.approx.f32 %f1, %f0;",
        ".reg .f32 %f0, %f1;",
        "mov.f32 %f0, 0f40000000;"))

    cases.append(fp_kernel("FP12", "rsqrt_approx_f32", "rsqrt.approx.f32 (SFU)",
        "rsqrt.approx.f32 %f1, %f0;",
        ".reg .f32 %f0, %f1;",
        "mov.f32 %f0, 0f40800000;"))

    cases.append(fp_kernel("FP13", "rcp_rn_f64", "rcp.rn.f64 (HIGH RISK: Newton-Raphson?)",
        "rcp.rn.f64 %fd1, %fd0;",
        ".reg .f64 %fd0, %fd1;",
        "mov.f64 %fd0, 0d4000000000000000;"))

    cases.append(fp_kernel("FP14", "sqrt_rn_f64", "sqrt.rn.f64 (HIGH RISK: multi-step?)",
        "sqrt.rn.f64 %fd1, %fd0;",
        ".reg .f64 %fd0, %fd1;",
        "mov.f64 %fd0, 0d4010000000000000;"))

    cases.append(fp_kernel("FP15", "add_f16x2", "add.f16x2 (FP16 vector)",
        "add.f16x2 %h2, %h0, %h1;",
        ".reg .b32 %h0, %h1, %h2;",
        "mov.b32 %h0, 0x3C003C00;\nmov.b32 %h1, 0x4000C000;"))

    cases.append(fp_kernel("FP16", "ex2_ftz_f32", "ex2.approx.ftz.f32 (FTZ variant)",
        "ex2.approx.ftz.f32 %f1, %f0;",
        ".reg .f32 %f0, %f1;",
        "mov.f32 %f0, 0f3F800000;"))

    return cases


# ===========================================================================
# 第七批: 类型转换
# ===========================================================================

def gen_cvt_cases() -> list[PTXTestCase]:
    cases = []

    def cvt_kernel(case_id, mnemonic, desc, instr, regs, setup):
        return PTXTestCase(
            batch="06_cuda_core_fp", case_id=case_id, mnemonic=mnemonic,
            description=desc,
            body=HEADER + f"""
// {case_id}: {desc}
.visible .entry test_{mnemonic}() {{
    {regs}

    {setup}

    // === target instruction ===
    {instr}

    ret;
}}
""")

    cases.append(cvt_kernel("C01", "cvt_f32_f64", "cvt.rn.f32.f64 (f64->f32)",
        "cvt.rn.f32.f64 %f0, %fd0;",
        ".reg .f64 %fd0;\n    .reg .f32 %f0;",
        "mov.f64 %fd0, 0d3FF0000000000000;"))

    cases.append(cvt_kernel("C02", "cvt_f64_f32", "cvt.f64.f32 (f32->f64)",
        "cvt.f64.f32 %fd0, %f0;",
        ".reg .f32 %f0;\n    .reg .f64 %fd0;",
        "mov.f32 %f0, 0f3F800000;"))

    cases.append(cvt_kernel("C03", "cvt_s32_f32", "cvt.rni.s32.f32 (float->int)",
        "cvt.rni.s32.f32 %r0, %f0;",
        ".reg .f32 %f0;\n    .reg .s32 %r0;",
        "mov.f32 %f0, 0f41280000;"))

    cases.append(cvt_kernel("C04", "cvt_f32_s32", "cvt.rn.f32.s32 (int->float)",
        "cvt.rn.f32.s32 %f0, %r0;",
        ".reg .s32 %r0;\n    .reg .f32 %f0;",
        "mov.s32 %r0, 42;"))

    cases.append(cvt_kernel("C05", "cvt_s64_s32", "cvt.s64.s32 (sign extend)",
        "cvt.s64.s32 %rd0, %r0;",
        ".reg .s32 %r0;\n    .reg .s64 %rd0;",
        "mov.s32 %r0, -42;"))

    cases.append(cvt_kernel("C06", "cvt_u32_u64", "cvt.u32.u64 (truncate)",
        "cvt.u32.u64 %r0, %rd0;",
        ".reg .u64 %rd0;\n    .reg .u32 %r0;",
        "mov.u64 %rd0, 0x00000000DEADBEEF;"))

    cases.append(cvt_kernel("C07", "cvt_f16_f32", "cvt.rn.f16.f32 (f32->f16)",
        "cvt.rn.f16.f32 %h0, %f0;",
        ".reg .f32 %f0;\n    .reg .f16 %h0;",
        "mov.f32 %f0, 0f3F800000;"))

    cases.append(cvt_kernel("C08", "cvt_f32_f16", "cvt.f32.f16 (f16->f32)",
        "cvt.f32.f16 %f0, %h0;",
        ".reg .f16 %h0;\n    .reg .f32 %f0;",
        "mov.b16 %h0, 0x3C00;"))

    cases.append(cvt_kernel("C09", "cvt_bf16_f32", "cvt.rn.bf16.f32 (f32->bf16)",
        "cvt.rn.bf16.f32 %bh0, %f0;",
        ".reg .f32 %f0;\n    .reg .b16 %bh0;",
        "mov.f32 %f0, 0f3F800000;"))

    cases.append(cvt_kernel("C10", "cvt_f32_bf16", "cvt.f32.bf16 (bf16->f32)",
        "cvt.f32.bf16 %f0, %bh0;",
        ".reg .b16 %bh0;\n    .reg .f32 %f0;",
        "mov.b16 %bh0, 0x3F80;"))

    # C11: cvt.rn.f16x2.f32 (packed F32->F16x2, epilogue critical)
    cases.append(cvt_kernel("C11", "cvt_f16x2_f32", "cvt.rn.f16x2.f32 (packed F32->F16x2, HIGH RISK)",
        "cvt.rn.f16x2.f32 %v0, %f0, %f1;",
        ".reg .f32 %f0, %f1;\n    .reg .b32 %v0;",
        "mov.f32 %f0, 0f3F800000;\nmov.f32 %f1, 0f40000000;"))

    # C12: cvt.rn.bf16x2.f32 (packed F32->BF16x2)
    cases.append(cvt_kernel("C12", "cvt_bf16x2_f32", "cvt.rn.bf16x2.f32 (packed F32->BF16x2, HIGH RISK)",
        "cvt.rn.bf16x2.f32 %v0, %f0, %f1;",
        ".reg .f32 %f0, %f1;\n    .reg .b32 %v0;",
        "mov.f32 %f0, 0f3F800000;\nmov.f32 %f1, 0f40000000;"))

    return cases


# ===========================================================================
# 第八批: LSU 访存
# ===========================================================================

def gen_lsu_cases() -> list[PTXTestCase]:
    cases = []

    # L01: ld.shared.b32
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L01", mnemonic="ld_shared_b32",
        description="ld.shared.b32",
        body=HEADER + """
.shared .align 4 .u32 smem_data[256];

.visible .entry test_ld_shared_b32() {
    .reg .u32 %r0;

    // === target instruction ===
    ld.shared.b32 %r0, [smem_data];

    ret;
}
"""))

    # L02: ld.shared.b64
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L02", mnemonic="ld_shared_b64",
        description="ld.shared.b64",
        body=HEADER + """
.shared .align 8 .u64 smem_data64[128];

.visible .entry test_ld_shared_b64() {
    .reg .b64 %rd0;

    // === target instruction ===
    ld.shared.b64 %rd0, [smem_data64];

    ret;
}
"""))

    # L03: ld.shared.b128
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L03", mnemonic="ld_shared_b128",
        description="ld.shared.b128 (128-bit, may split?)",
        body=HEADER + """
.shared .align 16 .u32 smem_data128[256];

.visible .entry test_ld_shared_b128() {
    .reg .b32 %r0, %r1, %r2, %r3;

    // === target instruction ===
    ld.shared.v4.b32 {%r0, %r1, %r2, %r3}, [smem_data128];

    ret;
}
"""))

    # L04: st.shared.b32
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L04", mnemonic="st_shared_b32",
        description="st.shared.b32",
        body=HEADER + """
.shared .align 4 .u32 smem_data[256];

.visible .entry test_st_shared_b32() {
    .reg .u32 %r0;
    mov.u32 %r0, 42;

    // === target instruction ===
    st.shared.b32 [smem_data], %r0;

    ret;
}
"""))

    # L05: st.shared.b64
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L05", mnemonic="st_shared_b64",
        description="st.shared.b64",
        body=HEADER + """
.shared .align 8 .u64 smem_data64[128];

.visible .entry test_st_shared_b64() {
    .reg .b64 %rd0;
    mov.b64 %rd0, 42;

    // === target instruction ===
    st.shared.b64 [smem_data64], %rd0;

    ret;
}
"""))

    # L06: st.shared.v4.b32 (128-bit store)
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L06", mnemonic="st_shared_b128",
        description="st.shared.v4.b32 (128-bit)",
        body=HEADER + """
.shared .align 16 .u32 smem_data128[256];

.visible .entry test_st_shared_b128() {
    .reg .b32 %r0, %r1, %r2, %r3;
    mov.b32 %r0, 1;
    mov.b32 %r1, 2;
    mov.b32 %r2, 3;
    mov.b32 %r3, 4;

    // === target instruction ===
    st.shared.v4.b32 [smem_data128], {%r0, %r1, %r2, %r3};

    ret;
}
"""))

    # L07: ld.global.b32
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L07", mnemonic="ld_global_b32",
        description="ld.global.b32",
        body=HEADER + """
.visible .entry test_ld_global_b32(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .u32 %r0;

    ld.param.u64 %addr, [p_addr];

    // === target instruction ===
    ld.global.b32 %r0, [%addr];

    ret;
}
"""))

    # L08: ld.global.b64
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L08", mnemonic="ld_global_b64",
        description="ld.global.b64",
        body=HEADER + """
.visible .entry test_ld_global_b64(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .b64 %rd0;

    ld.param.u64 %addr, [p_addr];

    // === target instruction ===
    ld.global.b64 %rd0, [%addr];

    ret;
}
"""))

    # L09: ld.global.v4.b32 (128-bit)
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L09", mnemonic="ld_global_b128",
        description="ld.global.v4.b32 (128-bit)",
        body=HEADER + """
.visible .entry test_ld_global_b128(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .b32 %r0, %r1, %r2, %r3;

    ld.param.u64 %addr, [p_addr];

    // === target instruction ===
    ld.global.v4.b32 {%r0, %r1, %r2, %r3}, [%addr];

    ret;
}
"""))

    # L10: st.global.b32
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L10", mnemonic="st_global_b32",
        description="st.global.b32",
        body=HEADER + """
.visible .entry test_st_global_b32(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .u32 %r0;

    ld.param.u64 %addr, [p_addr];
    mov.u32 %r0, 42;

    // === target instruction ===
    st.global.b32 [%addr], %r0;

    ret;
}
"""))

    # L11: st.global.b64
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L11", mnemonic="st_global_b64",
        description="st.global.b64",
        body=HEADER + """
.visible .entry test_st_global_b64(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .b64 %rd0;

    ld.param.u64 %addr, [p_addr];
    mov.b64 %rd0, 42;

    // === target instruction ===
    st.global.b64 [%addr], %rd0;

    ret;
}
"""))

    # L12: ld.param.u64
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L12", mnemonic="ld_param_u64",
        description="ld.param.u64",
        body=HEADER + """
.visible .entry test_ld_param_u64(
    .param .u64 p_val
) {
    .reg .u64 %rd0;

    // === target instruction ===
    ld.param.u64 %rd0, [p_val];

    ret;
}
"""))

    # L13: ld.shared.v2.b32 (64-bit vector)
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L13", mnemonic="ld_shared_v2b32",
        description="ld.shared.v2.b32 (64-bit vector)",
        body=HEADER + """
.shared .align 8 .u32 smem_data[256];

.visible .entry test_ld_shared_v2b32() {
    .reg .b32 %r0, %r1;

    // === target instruction ===
    ld.shared.v2.b32 {%r0, %r1}, [smem_data];

    ret;
}
"""))

    # L14: ld.shared.v2.b64 (128-bit vector)
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L14", mnemonic="ld_shared_v2b64",
        description="ld.shared.v2.b64 (128-bit vector)",
        body=HEADER + """
.shared .align 16 .u64 smem_data64[128];

.visible .entry test_ld_shared_v2b64() {
    .reg .b64 %rd0, %rd1;

    // === target instruction ===
    ld.shared.v2.b64 {%rd0, %rd1}, [smem_data64];

    ret;
}
"""))

    # L15: st.shared.v2.b32 (64-bit vector store)
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L15", mnemonic="st_shared_v2b32",
        description="st.shared.v2.b32 (64-bit vector store)",
        body=HEADER + """
.shared .align 8 .u32 smem_data[256];

.visible .entry test_st_shared_v2b32() {
    .reg .b32 %r0, %r1;
    mov.b32 %r0, 1;
    mov.b32 %r1, 2;

    // === target instruction ===
    st.shared.v2.b32 [smem_data], {%r0, %r1};

    ret;
}
"""))

    # L16: st.shared.v2.b64 (128-bit vector store)
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L16", mnemonic="st_shared_v2b64",
        description="st.shared.v2.b64 (128-bit vector store)",
        body=HEADER + """
.shared .align 16 .u64 smem_data64[128];

.visible .entry test_st_shared_v2b64() {
    .reg .b64 %rd0, %rd1;
    mov.b64 %rd0, 1;
    mov.b64 %rd1, 2;

    // === target instruction ===
    st.shared.v2.b64 [smem_data64], {%rd0, %rd1};

    ret;
}
"""))

    # L17: ld.global.nc (non-coherent load, __ldg equivalent)
    cases.append(PTXTestCase(
        batch="07_lsu", case_id="L17", mnemonic="ld_global_nc",
        description="ld.global.nc.b32 (non-coherent, __ldg equivalent)",
        body=HEADER + """
.visible .entry test_ld_global_nc(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .u32 %r0;

    ld.param.u64 %addr, [p_addr];

    // === target instruction ===
    ld.global.nc.b32 %r0, [%addr];

    ret;
}
"""))

    return cases


# ===========================================================================
# 第九批: 特殊寄存器与控制流
# ===========================================================================

def gen_special_cases() -> list[PTXTestCase]:
    cases = []

    # S01: mov %tid.x
    cases.append(PTXTestCase(
        batch="08_control_flow", case_id="S01", mnemonic="mov_tid_x",
        description="mov.u32 %r, %tid.x (S2R)",
        body=HEADER + """
.visible .entry test_mov_tid_x() {
    .reg .u32 %r0;

    // === target instruction ===
    mov.u32 %r0, %tid.x;

    ret;
}
"""))

    # S02: mov %ctaid.x
    cases.append(PTXTestCase(
        batch="08_control_flow", case_id="S02", mnemonic="mov_ctaid_x",
        description="mov.u32 %r, %ctaid.x (S2R)",
        body=HEADER + """
.visible .entry test_mov_ctaid_x() {
    .reg .u32 %r0;

    // === target instruction ===
    mov.u32 %r0, %ctaid.x;

    ret;
}
"""))

    # S03: mov %laneid
    cases.append(PTXTestCase(
        batch="08_control_flow", case_id="S03", mnemonic="mov_laneid",
        description="mov.u32 %r, %laneid (S2R)",
        body=HEADER + """
.visible .entry test_mov_laneid() {
    .reg .u32 %r0;

    // === target instruction ===
    mov.u32 %r0, %laneid;

    ret;
}
"""))

    # S04: bra (unconditional)
    cases.append(PTXTestCase(
        batch="08_control_flow", case_id="S04", mnemonic="bra_uncond",
        description="bra (unconditional branch)",
        body=HEADER + """
.visible .entry test_bra_uncond() {
    // === target instruction ===
    bra END;
END:
    ret;
}
"""))

    # S05: @%p bra (conditional)
    cases.append(PTXTestCase(
        batch="08_control_flow", case_id="S05", mnemonic="bra_cond",
        description="@%p bra (conditional branch)",
        body=HEADER + """
.visible .entry test_bra_cond() {
    .reg .u32 %r0;
    .reg .pred %p0;

    mov.u32 %r0, %tid.x;
    setp.eq.u32 %p0, %r0, 0;

    // === target instruction ===
    @%p0 bra END;
END:
    ret;
}
"""))

    # S06: ret
    cases.append(PTXTestCase(
        batch="08_control_flow", case_id="S06", mnemonic="ret",
        description="ret",
        body=HEADER + """
.visible .entry test_ret() {
    // === target instruction ===
    ret;
}
"""))

    return cases


# ===========================================================================
# 第十批: 原子操作 (可选)
# ===========================================================================

def gen_atomic_cases() -> list[PTXTestCase]:
    cases = []

    # A01: atom.global.add.u32
    cases.append(PTXTestCase(
        batch="10_atomic", case_id="A01", mnemonic="atom_global_add_u32",
        description="atom.global.add.u32",
        body=HEADER + """
.visible .entry test_atom_global_add_u32(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .u32 %r0, %old;

    ld.param.u64 %addr, [p_addr];
    mov.u32 %r0, 1;

    // === target instruction ===
    atom.global.add.u32 %old, [%addr], %r0;

    ret;
}
"""))

    # A02: atom.global.add.u64 (HIGH RISK)
    cases.append(PTXTestCase(
        batch="10_atomic", case_id="A02", mnemonic="atom_global_add_u64",
        description="atom.global.add.u64 (HIGH RISK: 64-bit atomic)",
        body=HEADER + """
.visible .entry test_atom_global_add_u64(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .u64 %val, %old;

    ld.param.u64 %addr, [p_addr];
    mov.u64 %val, 1;

    // === target instruction ===
    atom.global.add.u64 %old, [%addr], %val;

    ret;
}
"""))

    # A03: atom.global.cas.b32
    cases.append(PTXTestCase(
        batch="10_atomic", case_id="A03", mnemonic="atom_global_cas_b32",
        description="atom.global.cas.b32",
        body=HEADER + """
.visible .entry test_atom_global_cas_b32(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .b32 %cmp, %new_val, %old;

    ld.param.u64 %addr, [p_addr];
    mov.b32 %cmp, 0;
    mov.b32 %new_val, 1;

    // === target instruction ===
    atom.global.cas.b32 %old, [%addr], %cmp, %new_val;

    ret;
}
"""))

    # A04: atom.global.cas.b64 (HIGH RISK)
    cases.append(PTXTestCase(
        batch="10_atomic", case_id="A04", mnemonic="atom_global_cas_b64",
        description="atom.global.cas.b64 (HIGH RISK: 64-bit CAS)",
        body=HEADER + """
.visible .entry test_atom_global_cas_b64(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .b64 %cmp, %new_val, %old;

    ld.param.u64 %addr, [p_addr];
    mov.b64 %cmp, 0;
    mov.b64 %new_val, 1;

    // === target instruction ===
    atom.global.cas.b64 %old, [%addr], %cmp, %new_val;

    ret;
}
"""))

    # A05: atom.shared.add.u32
    cases.append(PTXTestCase(
        batch="10_atomic", case_id="A05", mnemonic="atom_shared_add_u32",
        description="atom.shared.add.u32",
        body=HEADER + """
.shared .align 4 .u32 smem_atomic;

.visible .entry test_atom_shared_add_u32() {
    .reg .u32 %r0, %old;
    mov.u32 %r0, 1;

    // === target instruction ===
    atom.shared.add.u32 %old, [smem_atomic], %r0;

    ret;
}
"""))

    # A06: red.global.add.u32 (reduction without return, attention normalization)
    cases.append(PTXTestCase(
        batch="10_atomic", case_id="A06", mnemonic="red_global_add_u32",
        description="red.global.add.u32 (no return value, attention norm)",
        body=HEADER + """
.visible .entry test_red_global_add_u32(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .u32 %r0;

    ld.param.u64 %addr, [p_addr];
    mov.u32 %r0, 1;

    // === target instruction ===
    red.global.add.u32 [%addr], %r0;

    ret;
}
"""))

    return cases


# ===========================================================================
# 第十一批: Half Precision f16/f16x2 完整算术
# ===========================================================================

def gen_half_precision_cases() -> list[PTXTestCase]:
    cases = []

    def hp_kernel(case_id, mnemonic, desc, instr, regs, setup):
        return PTXTestCase(
            batch="11_half_precision", case_id=case_id, mnemonic=mnemonic,
            description=desc,
            body=HEADER + f"""
// {case_id}: {desc}
.visible .entry test_{mnemonic}() {{
    {regs}

    {setup}

    // === target instruction ===
    {instr}

    ret;
}}
""")

    cases.append(hp_kernel("H01", "add_f16", "add.f16",
        "add.f16 %h2, %h0, %h1;",
        ".reg .f16 %h0, %h1, %h2;",
        "mov.b16 %h0, 0x3C00;\nmov.b16 %h1, 0x4000;"))

    cases.append(hp_kernel("H02", "sub_f16", "sub.f16",
        "sub.f16 %h2, %h0, %h1;",
        ".reg .f16 %h0, %h1, %h2;",
        "mov.b16 %h0, 0x4000;\nmov.b16 %h1, 0x3C00;"))

    cases.append(hp_kernel("H03", "mul_f16", "mul.f16",
        "mul.f16 %h2, %h0, %h1;",
        ".reg .f16 %h0, %h1, %h2;",
        "mov.b16 %h0, 0x3C00;\nmov.b16 %h1, 0x4000;"))

    cases.append(hp_kernel("H04", "fma_f16", "fma.rn.f16",
        "fma.rn.f16 %h2, %h0, %h1, %h2;",
        ".reg .f16 %h0, %h1, %h2;",
        "mov.b16 %h0, 0x3C00;\nmov.b16 %h1, 0x4000;\nmov.b16 %h2, 0x0000;"))

    cases.append(hp_kernel("H05", "add_f16x2", "add.f16x2",
        "add.f16x2 %v2, %v0, %v1;",
        ".reg .b32 %v0, %v1, %v2;",
        "mov.b32 %v0, 0x3C003C00;\nmov.b32 %v1, 0x40004000;"))

    cases.append(hp_kernel("H06", "sub_f16x2", "sub.f16x2",
        "sub.f16x2 %v2, %v0, %v1;",
        ".reg .b32 %v0, %v1, %v2;",
        "mov.b32 %v0, 0x40004000;\nmov.b32 %v1, 0x3C003C00;"))

    cases.append(hp_kernel("H07", "mul_f16x2", "mul.f16x2",
        "mul.f16x2 %v2, %v0, %v1;",
        ".reg .b32 %v0, %v1, %v2;",
        "mov.b32 %v0, 0x3C003C00;\nmov.b32 %v1, 0x40004000;"))

    cases.append(hp_kernel("H08", "fma_f16x2", "fma.rn.f16x2",
        "fma.rn.f16x2 %v2, %v0, %v1, %v2;",
        ".reg .b32 %v0, %v1, %v2;",
        "mov.b32 %v0, 0x3C003C00;\nmov.b32 %v1, 0x40004000;\nmov.b32 %v2, 0x00000000;"))

    cases.append(hp_kernel("H09", "max_f16x2", "max.f16x2",
        "max.f16x2 %v2, %v0, %v1;",
        ".reg .b32 %v0, %v1, %v2;",
        "mov.b32 %v0, 0x3C003C00;\nmov.b32 %v1, 0x40004000;"))

    cases.append(hp_kernel("H10", "min_f16x2", "min.f16x2",
        "min.f16x2 %v2, %v0, %v1;",
        ".reg .b32 %v0, %v1, %v2;",
        "mov.b32 %v0, 0x3C003C00;\nmov.b32 %v1, 0x40004000;"))

    cases.append(hp_kernel("H11", "neg_f16x2", "neg.f16x2",
        "neg.f16x2 %v1, %v0;",
        ".reg .b32 %v0, %v1;",
        "mov.u32 %v0, %clock;"))

    cases.append(hp_kernel("H12", "abs_f16x2", "abs.f16x2",
        "abs.f16x2 %v1, %v0;",
        ".reg .b32 %v0, %v1;",
        "mov.u32 %v0, %clock;"))

    cases.append(hp_kernel("H13", "max_f16", "max.f16",
        "max.f16 %h2, %h0, %h1;",
        ".reg .f16 %h0, %h1, %h2;",
        "mov.b16 %h0, 0x3C00;\nmov.b16 %h1, 0x4000;"))

    cases.append(hp_kernel("H14", "min_f16", "min.f16",
        "min.f16 %h2, %h0, %h1;",
        ".reg .f16 %h0, %h1, %h2;",
        "mov.b16 %h0, 0x3C00;\nmov.b16 %h1, 0x4000;"))

    cases.append(hp_kernel("H15", "setp_f16", "setp.gt.f16",
        "setp.gt.f16 %p0, %h0, %h1;",
        ".reg .f16 %h0, %h1;\n    .reg .pred %p0;",
        "mov.b16 %h0, 0x4000;\nmov.b16 %h1, 0x3C00;"))

    return cases


# ===========================================================================
# 第十二批: BF16/BF16x2 算术
# ===========================================================================

def gen_bf16_cases() -> list[PTXTestCase]:
    cases = []

    def bf_kernel(case_id, mnemonic, desc, instr, regs, setup):
        return PTXTestCase(
            batch="12_bf16", case_id=case_id, mnemonic=mnemonic,
            description=desc,
            body=HEADER + f"""
// {case_id}: {desc}
.visible .entry test_{mnemonic}() {{
    {regs}

    {setup}

    // === target instruction ===
    {instr}

    ret;
}}
""")

    cases.append(bf_kernel("BF01", "add_bf16", "add.bf16",
        "add.bf16 %b2, %b0, %b1;",
        ".reg .b16 %b0, %b1, %b2;",
        "mov.b16 %b0, 0x3F80;\nmov.b16 %b1, 0x4000;"))

    cases.append(bf_kernel("BF02", "sub_bf16", "sub.bf16",
        "sub.bf16 %b2, %b0, %b1;",
        ".reg .b16 %b0, %b1, %b2;",
        "mov.b16 %b0, 0x4000;\nmov.b16 %b1, 0x3F80;"))

    cases.append(bf_kernel("BF03", "mul_bf16", "mul.bf16",
        "mul.bf16 %b2, %b0, %b1;",
        ".reg .b16 %b0, %b1, %b2;",
        "mov.b16 %b0, 0x3F80;\nmov.b16 %b1, 0x4000;"))

    cases.append(bf_kernel("BF04", "fma_bf16", "fma.rn.bf16",
        "fma.rn.bf16 %b2, %b0, %b1, %b2;",
        ".reg .b16 %b0, %b1, %b2;",
        "mov.b16 %b0, 0x3F80;\nmov.b16 %b1, 0x4000;\nmov.b16 %b2, 0x0000;"))

    cases.append(bf_kernel("BF05", "add_bf16x2", "add.bf16x2",
        "add.bf16x2 %v2, %v0, %v1;",
        ".reg .b32 %v0, %v1, %v2;",
        "mov.b32 %v0, 0x3F803F80;\nmov.b32 %v1, 0x40004000;"))

    cases.append(bf_kernel("BF06", "sub_bf16x2", "sub.bf16x2",
        "sub.bf16x2 %v2, %v0, %v1;",
        ".reg .b32 %v0, %v1, %v2;",
        "mov.b32 %v0, 0x40004000;\nmov.b32 %v1, 0x3F803F80;"))

    cases.append(bf_kernel("BF07", "mul_bf16x2", "mul.bf16x2",
        "mul.bf16x2 %v2, %v0, %v1;",
        ".reg .b32 %v0, %v1, %v2;",
        "mov.b32 %v0, 0x3F803F80;\nmov.b32 %v1, 0x40004000;"))

    cases.append(bf_kernel("BF08", "fma_bf16x2", "fma.rn.bf16x2",
        "fma.rn.bf16x2 %v2, %v0, %v1, %v2;",
        ".reg .b32 %v0, %v1, %v2;",
        "mov.b32 %v0, 0x3F803F80;\nmov.b32 %v1, 0x40004000;\nmov.b32 %v2, 0x00000000;"))

    cases.append(bf_kernel("BF09", "max_bf16x2", "max.bf16x2",
        "max.bf16x2 %v2, %v0, %v1;",
        ".reg .b32 %v0, %v1, %v2;",
        "mov.b32 %v0, 0x3F803F80;\nmov.b32 %v1, 0x40004000;"))

    cases.append(bf_kernel("BF10", "neg_bf16x2", "neg.bf16x2",
        "neg.bf16x2 %v1, %v0;",
        ".reg .b32 %v0, %v1;",
        "mov.b32 %v0, 0x3F803F80;"))

    return cases


# ===========================================================================
# 第十三批: Warp 级跨 lane 通信
# ===========================================================================

def gen_warp_comm_cases() -> list[PTXTestCase]:
    cases = []

    def wc_kernel(case_id, mnemonic, desc, instr, regs, setup,
                  unsupported_reason=""):
        unsupported_marker = (
            f"// EXPECTED_UNSUPPORTED_BY_PTX_ISA: {unsupported_reason}\n"
            if unsupported_reason else ""
        )
        return PTXTestCase(
            batch="13_warp_comm", case_id=case_id, mnemonic=mnemonic,
            description=desc,
            body=HEADER + f"""
// {case_id}: {desc}
{unsupported_marker}.visible .entry test_{mnemonic}() {{
    {regs}

    {setup}

    // === target instruction ===
    {instr}

    ret;
}}
""")

    # shfl.sync variants
    cases.append(wc_kernel("W01", "shfl_bfly", "shfl.sync.bfly.b32 (butterfly)",
        "shfl.sync.bfly.b32 %r1, %r0, 1, 0x1f, 0xFFFFFFFF;",
        ".reg .b32 %r0, %r1;",
        "mov.b32 %r0, %tid.x;"))

    cases.append(wc_kernel("W02", "shfl_up", "shfl.sync.up.b32",
        "shfl.sync.up.b32 %r1, %r0, 1, 0, 0xFFFFFFFF;",
        ".reg .b32 %r0, %r1;",
        "mov.b32 %r0, %tid.x;"))

    cases.append(wc_kernel("W03", "shfl_down", "shfl.sync.down.b32",
        "shfl.sync.down.b32 %r1, %r0, 1, 0x1f, 0xFFFFFFFF;",
        ".reg .b32 %r0, %r1;",
        "mov.b32 %r0, %tid.x;"))

    cases.append(wc_kernel("W04", "shfl_idx", "shfl.sync.idx.b32",
        "shfl.sync.idx.b32 %r1, %r0, 0, 0x1f, 0xFFFFFFFF;",
        ".reg .b32 %r0, %r1;",
        "mov.b32 %r0, %tid.x;"))

    # redux.sync variants
    cases.append(wc_kernel("W05", "redux_add_s32", "redux.sync.add.s32",
        "redux.sync.add.s32 %r1, %r0, 0xFFFFFFFF;",
        ".reg .s32 %r0, %r1;",
        "mov.s32 %r0, 1;"))

    cases.append(wc_kernel("W06", "redux_max_s32", "redux.sync.max.s32",
        "redux.sync.max.s32 %r1, %r0, 0xFFFFFFFF;",
        ".reg .s32 %r0, %r1;",
        "mov.s32 %r0, %tid.x;"))

    cases.append(wc_kernel("W07", "redux_add_f32", "redux.sync.add.f32 (negative test)",
        "redux.sync.add.f32 %f1, %f0, 0xFFFFFFFF;",
        ".reg .f32 %f0, %f1;",
        "mov.f32 %f0, 0f3F800000;",
        "PTX ISA 9.3 permits .add only with .u32/.s32; .f32 permits only .min/.max"))

    cases.append(wc_kernel("W08", "redux_max_f32", "redux.sync.max.f32 (sm_100 new)",
        "redux.sync.max.f32 %f1, %f0, 0xFFFFFFFF;",
        ".reg .f32 %f0, %f1;",
        "mov.f32 %f0, 0f3F800000;"))

    cases.append(wc_kernel("W09", "redux_xor_b32", "redux.sync.xor.b32",
        "redux.sync.xor.b32 %r1, %r0, 0xFFFFFFFF;",
        ".reg .b32 %r0, %r1;",
        "mov.b32 %r0, %tid.x;"))

    # vote.sync
    cases.append(wc_kernel("W10", "vote_all", "vote.sync.all.pred",
        "vote.sync.all.pred %p1, %p0, 0xFFFFFFFF;",
        ".reg .pred %p0, %p1;\n    .reg .u32 %lane;",
        "mov.u32 %lane, %tid.x;\nsetp.gt.u32 %p0, %lane, 0;"))

    cases.append(wc_kernel("W11", "vote_any", "vote.sync.any.pred",
        "vote.sync.any.pred %p1, %p0, 0xFFFFFFFF;",
        ".reg .pred %p0, %p1;\n    .reg .u32 %lane;",
        "mov.u32 %lane, %tid.x;\nsetp.eq.u32 %p0, %lane, 0;"))

    cases.append(wc_kernel("W12", "vote_ballot", "vote.sync.ballot.b32",
        "vote.sync.ballot.b32 %r0, %p0, 0xFFFFFFFF;",
        ".reg .pred %p0;\n    .reg .b32 %r0;\n    .reg .u32 %lane;",
        "mov.u32 %lane, %tid.x;\nsetp.gt.u32 %p0, %lane, 15;"))

    # match.sync
    cases.append(wc_kernel("W13", "match_any", "match.sync.any.b32",
        "match.sync.any.b32 %r1, %r0, 0xFFFFFFFF;",
        ".reg .b32 %r0, %r1;",
        "mov.b32 %r0, %tid.x;"))

    # elect.sync
    cases.append(wc_kernel("W14", "elect_sync", "elect.sync (leader election)",
        "elect.sync %r0|%p0, 0xFFFFFFFF;",
        ".reg .b32 %r0;\n    .reg .pred %p0;",
        "// no setup"))

    return cases


# ===========================================================================
# 第十四批: 位操作
# ===========================================================================

def gen_bit_ops_cases() -> list[PTXTestCase]:
    cases = []

    def bit_kernel(case_id, mnemonic, desc, instr, regs, setup):
        return PTXTestCase(
            batch="14_bit_ops", case_id=case_id, mnemonic=mnemonic,
            description=desc,
            body=HEADER + f"""
// {case_id}: {desc}
.visible .entry test_{mnemonic}() {{
    {regs}

    {setup}

    // === target instruction ===
    {instr}

    ret;
}}
""")

    cases.append(bit_kernel("BT01", "lop3_b32", "lop3.b32 (3-input logic)",
        "lop3.b32 %r3, %r0, %r1, %r2, 0xE8;",
        ".reg .b32 %r0, %r1, %r2, %r3;",
        "mov.b32 %r0, 0xFF00FF00;\nmov.b32 %r1, 0xF0F0F0F0;\nmov.b32 %r2, 0xCCCCCCCC;"))

    cases.append(bit_kernel("BT02", "prmt_b32", "prmt.b32 (byte permute)",
        "prmt.b32 %r2, %r0, %r1, 0x3210;",
        ".reg .b32 %r0, %r1, %r2;",
        "mov.b32 %r0, 0xAABBCCDD;\nmov.b32 %r1, 0x11223344;"))

    cases.append(bit_kernel("BT03", "prmt_f4e", "prmt.b32.f4e (funnel extract)",
        "prmt.b32.f4e %r2, %r0, %r1, 0x5432;",
        ".reg .b32 %r0, %r1, %r2;",
        "mov.b32 %r0, 0xAABBCCDD;\nmov.b32 %r1, 0x11223344;"))

    cases.append(bit_kernel("BT04", "bfe_u32", "bfe.u32 (bit field extract)",
        "bfe.u32 %r1, %r0, 8, 4;",
        ".reg .u32 %r0, %r1;",
        "mov.u32 %r0, 0xDEADBEEF;"))

    cases.append(bit_kernel("BT05", "bfe_s32", "bfe.s32 (signed bit field extract)",
        "bfe.s32 %r1, %r0, 8, 4;",
        ".reg .s32 %r0, %r1;",
        "mov.s32 %r0, 0xDEADBEEF;"))

    cases.append(bit_kernel("BT06", "bfi_b32", "bfi.b32 (bit field insert)",
        "bfi.b32 %r2, %r0, %r1, 8, 4;",
        ".reg .b32 %r0, %r1, %r2;",
        "mov.b32 %r0, 0x0000000F;\nmov.b32 %r1, 0xDEAD0000;"))

    cases.append(bit_kernel("BT07", "popc_b32", "popc.b32 (population count)",
        "popc.b32 %r1, %r0;",
        ".reg .b32 %r0;\n    .reg .u32 %r1;",
        "mov.b32 %r0, 0xFF00FF00;"))

    cases.append(bit_kernel("BT08", "clz_b32", "clz.b32 (count leading zeros)",
        "clz.b32 %r1, %r0;",
        ".reg .b32 %r0;\n    .reg .u32 %r1;",
        "mov.b32 %r0, 0x00FF0000;"))

    cases.append(bit_kernel("BT09", "brev_b32", "brev.b32 (bit reverse)",
        "brev.b32 %r1, %r0;",
        ".reg .b32 %r0, %r1;",
        "mov.b32 %r0, 0x80000001;"))

    cases.append(bit_kernel("BT10", "fns_b32", "fns.b32 (find n-th set bit)",
        "fns.b32 %r2, %r0, 0, %r1;",
        ".reg .b32 %r0, %r1;\n    .reg .u32 %r2;",
        "mov.b32 %r0, 0xFF00FF00;\nmov.b32 %r1, 3;"))

    cases.append(bit_kernel("BT11", "bmsk_b32", "bmsk.clamp.b32 (bitmask generation)",
        "bmsk.clamp.b32 %r2, %r0, %r1;",
        ".reg .b32 %r0, %r1, %r2;",
        "mov.b32 %r0, 4;\nmov.b32 %r1, 8;"))

    return cases


# ===========================================================================
# 第十五批: Cluster / DSMEM
# ===========================================================================

def gen_cluster_dsmem_cases() -> list[PTXTestCase]:
    cases = []

    # CL01: mapa
    cases.append(PTXTestCase(
        batch="15_cluster_dsmem", case_id="CL01", mnemonic="mapa_shared_cluster",
        description="mapa.shared::cluster (DSMEM address mapping)",
        body=HEADER + """
// CL01: mapa.shared::cluster
.shared .align 4 .u32 smem_data[256];

.visible .entry test_mapa() {
    .reg .u32 %r0, %rank;
    .reg .u32 %addr;

    mov.u32 %rank, 0;

    // === target instruction ===
    mapa.shared::cluster.u32 %addr, smem_data, %rank;

    ret;
}
"""))

    # CL02: getctarank
    cases.append(PTXTestCase(
        batch="15_cluster_dsmem", case_id="CL02", mnemonic="getctarank",
        description="getctarank (get CTA rank in cluster)",
        body=HEADER + """
// CL02: getctarank
.shared .align 4 .u32 smem_data[256];

.visible .entry test_getctarank() {
    .reg .u32 %rank;
    .reg .u32 %addr;

    mov.u32 %addr, smem_data;

    // === target instruction ===
    getctarank.shared::cluster.u32 %rank, %addr;

    ret;
}
"""))

    # CL03: cvta.shared.shared::cta
    cases.append(PTXTestCase(
        batch="15_cluster_dsmem", case_id="CL03", mnemonic="cvta_shared_cta",
        description="cvta.shared::cta.shared (addr space conversion)",
        body=HEADER + """
// CL03: cvta.shared::cta.shared
.shared .align 4 .u32 smem_data[256];

.visible .entry test_cvta_shared_cta() {
    .reg .u64 %gen_addr;

    // === target instruction ===
    cvta.shared::cta.u64 %gen_addr, smem_data;

    ret;
}
"""))

    # CL04: isspacep
    cases.append(PTXTestCase(
        batch="15_cluster_dsmem", case_id="CL04", mnemonic="isspacep_shared",
        description="isspacep.shared (address space query)",
        body=HEADER + """
// CL04: isspacep.shared
.visible .entry test_isspacep(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    .reg .pred %is_shared;

    ld.param.u64 %addr, [p_addr];

    // === target instruction ===
    isspacep.shared %is_shared, %addr;

    ret;
}
"""))

    # CL05: ld.shared::cluster
    cases.append(PTXTestCase(
        batch="15_cluster_dsmem", case_id="CL05", mnemonic="ld_shared_cluster",
        description="ld.shared::cluster.b32 (DSMEM cross-CTA read)",
        body=HEADER + """
// CL05: ld.shared::cluster.b32
.shared .align 4 .u32 smem_data[256];

.visible .entry test_ld_shared_cluster() {
    .reg .u32 %r0, %rank;
    .reg .u32 %remote_addr;

    mov.u32 %rank, 0;
    mapa.shared::cluster.u32 %remote_addr, smem_data, %rank;

    // === target instruction ===
    ld.shared::cluster.b32 %r0, [%remote_addr];

    ret;
}
"""))

    # CL06: st.shared::cluster
    cases.append(PTXTestCase(
        batch="15_cluster_dsmem", case_id="CL06", mnemonic="st_shared_cluster",
        description="st.shared::cluster.b32 (DSMEM cross-CTA write)",
        body=HEADER + """
// CL06: st.shared::cluster.b32
.shared .align 4 .u32 smem_data[256];

.visible .entry test_st_shared_cluster() {
    .reg .u32 %r0, %rank;
    .reg .u32 %remote_addr;

    mov.u32 %r0, 42;
    mov.u32 %rank, 0;
    mapa.shared::cluster.u32 %remote_addr, smem_data, %rank;

    // === target instruction ===
    st.shared::cluster.b32 [%remote_addr], %r0;

    ret;
}
"""))

    return cases


# ===========================================================================
# 第十六批: Megakernel 控制流
# ===========================================================================

def gen_megakernel_ctrl_cases() -> list[PTXTestCase]:
    cases = []

    # MK01: bar.warp.sync
    cases.append(PTXTestCase(
        batch="16_megakernel_ctrl", case_id="MK01", mnemonic="bar_warp_sync",
        description="bar.warp.sync (warp-level barrier)",
        body=HEADER + """
// MK01: bar.warp.sync
.visible .entry test_bar_warp_sync() {
    // === target instruction ===
    bar.warp.sync 0xFFFFFFFF;

    ret;
}
"""))

    # MK02: nanosleep
    cases.append(PTXTestCase(
        batch="16_megakernel_ctrl", case_id="MK02", mnemonic="nanosleep",
        description="nanosleep (spin-wait for producer-consumer)",
        body=HEADER + """
// MK02: nanosleep
.visible .entry test_nanosleep() {
    // === target instruction ===
    nanosleep.u32 100;

    ret;
}
"""))

    # MK03: griddepcontrol.launch_dependents
    cases.append(PTXTestCase(
        batch="16_megakernel_ctrl", case_id="MK03", mnemonic="griddep_launch",
        description="griddepcontrol.launch_dependents",
        body=HEADER + """
// MK03: griddepcontrol.launch_dependents
.visible .entry test_griddep_launch() {
    // === target instruction ===
    griddepcontrol.launch_dependents;

    ret;
}
"""))

    # MK04: griddepcontrol.wait
    cases.append(PTXTestCase(
        batch="16_megakernel_ctrl", case_id="MK04", mnemonic="griddep_wait",
        description="griddepcontrol.wait",
        body=HEADER + """
// MK04: griddepcontrol.wait
.visible .entry test_griddep_wait() {
    // === target instruction ===
    griddepcontrol.wait;

    ret;
}
"""))

    # MK05: prefetch.global.L2
    cases.append(PTXTestCase(
        batch="16_megakernel_ctrl", case_id="MK05", mnemonic="prefetch_global_L2",
        description="prefetch.global.L2 (non-TMA prefetch)",
        body=HEADER + """
// MK05: prefetch.global.L2
.visible .entry test_prefetch_global(
    .param .u64 p_addr
) {
    .reg .u64 %addr;
    ld.param.u64 %addr, [p_addr];

    // === target instruction ===
    prefetch.global.L2 [%addr];

    ret;
}
"""))

    return cases


# ===========================================================================
# 第十七批: 量化推理指令
# ===========================================================================

def gen_quantization_cases() -> list[PTXTestCase]:
    cases = []

    def q_kernel(case_id, mnemonic, desc, instr, regs, setup):
        return PTXTestCase(
            batch="17_quantization", case_id=case_id, mnemonic=mnemonic,
            description=desc,
            body=HEADER + f"""
// {case_id}: {desc}
.visible .entry test_{mnemonic}() {{
    {regs}

    {setup}

    // === target instruction ===
    {instr}

    ret;
}}
""")

    # dp4a
    cases.append(q_kernel("Q01", "dp4a_u32", "dp4a.u32.u32 (INT8 dot product)",
        "dp4a.u32.u32 %r2, %r0, %r1, %r2;",
        ".reg .u32 %r0, %r1, %r2;",
        "mov.u32 %r0, 0x01020304;\nmov.u32 %r1, 0x01010101;\nmov.u32 %r2, 0;"))

    cases.append(q_kernel("Q02", "dp4a_s32", "dp4a.s32.s32 (signed INT8 dot product)",
        "dp4a.s32.s32 %r2, %r0, %r1, %r2;",
        ".reg .s32 %r0, %r1, %r2;",
        "mov.s32 %r0, 0x01020304;\nmov.s32 %r1, 0x01010101;\nmov.s32 %r2, 0;"))

    # dp2a
    cases.append(q_kernel("Q03", "dp2a_lo", "dp2a.lo.u32.u32 (INT16 dot product lo)",
        "dp2a.lo.u32.u32 %r2, %r0, %r1, %r2;",
        ".reg .u32 %r0, %r1, %r2;",
        "mov.u32 %r0, 0x00010002;\nmov.u32 %r1, 0x00030004;\nmov.u32 %r2, 0;"))

    cases.append(q_kernel("Q04", "dp2a_hi", "dp2a.hi.u32.u32 (INT16 dot product hi)",
        "dp2a.hi.u32.u32 %r2, %r0, %r1, %r2;",
        ".reg .u32 %r0, %r1, %r2;",
        "mov.u32 %r0, 0x00010002;\nmov.u32 %r1, 0x00030004;\nmov.u32 %r2, 0;"))

    # cvt.pack
    cases.append(q_kernel("Q05", "cvt_pack_s8", "cvt.pack.sat.s8.s32.b32 (INT8 pack)",
        "cvt.pack.sat.s8.s32.b32 %r2, %r0, %r1, 0;",
        ".reg .s32 %r0, %r1;\n    .reg .b32 %r2;",
        "mov.s32 %r0, 42;\nmov.s32 %r1, -10;"))

    cases.append(q_kernel("Q06", "cvt_pack_u8", "cvt.pack.sat.u8.s32.b32 (UINT8 pack)",
        "cvt.pack.sat.u8.s32.b32 %r2, %r0, %r1, 0;",
        ".reg .s32 %r0, %r1;\n    .reg .b32 %r2;",
        "mov.s32 %r0, 200;\nmov.s32 %r1, 100;"))

    # FP8 conversions (sm_100)
    cases.append(q_kernel("Q07", "cvt_e4m3x2_f32", "cvt.rn.satfinite.e4m3x2.f32 (FP8 E4M3)",
        "cvt.rn.satfinite.e4m3x2.f32 %rs0, %f0, %f1;",
        ".reg .f32 %f0, %f1;\n    .reg .b16 %rs0;",
        "mov.f32 %f0, 0f3F800000;\nmov.f32 %f1, 0f40000000;"))

    cases.append(q_kernel("Q08", "cvt_e5m2x2_f32", "cvt.rn.satfinite.e5m2x2.f32 (FP8 E5M2)",
        "cvt.rn.satfinite.e5m2x2.f32 %rs0, %f0, %f1;",
        ".reg .f32 %f0, %f1;\n    .reg .b16 %rs0;",
        "mov.f32 %f0, 0f3F800000;\nmov.f32 %f1, 0f40000000;"))

    return cases


# ===========================================================================
# 第十八批: 激活函数
# ===========================================================================

def gen_activation_cases() -> list[PTXTestCase]:
    cases = []

    def act_kernel(case_id, mnemonic, desc, instr, regs, setup):
        return PTXTestCase(
            batch="18_activation", case_id=case_id, mnemonic=mnemonic,
            description=desc,
            body=HEADER + f"""
// {case_id}: {desc}
.visible .entry test_{mnemonic}() {{
    {regs}

    {setup}

    // === target instruction ===
    {instr}

    ret;
}}
""")

    cases.append(act_kernel("ACT01", "tanh_f16", "tanh.approx.f16 (GELU approx)",
        "tanh.approx.f16 %h1, %h0;",
        ".reg .f16 %h0, %h1;",
        "mov.b16 %h0, 0x3C00;"))

    cases.append(act_kernel("ACT02", "tanh_f16x2", "tanh.approx.f16x2 (vectorized GELU)",
        "tanh.approx.f16x2 %v1, %v0;",
        ".reg .b32 %v0, %v1;",
        "mov.b32 %v0, 0x3C003C00;"))

    cases.append(act_kernel("ACT03", "tanh_bf16", "tanh.approx.bf16",
        "tanh.approx.bf16 %b1, %b0;",
        ".reg .b16 %b0, %b1;",
        "mov.b16 %b0, 0x3F80;"))

    cases.append(act_kernel("ACT04", "tanh_bf16x2", "tanh.approx.bf16x2 (vectorized)",
        "tanh.approx.bf16x2 %v1, %v0;",
        ".reg .b32 %v0, %v1;",
        "mov.b32 %v0, 0x3F803F80;"))

    cases.append(act_kernel("ACT05", "ex2_f16", "ex2.approx.f16 (softmax exp)",
        "ex2.approx.f16 %h1, %h0;",
        ".reg .f16 %h0, %h1;",
        "mov.b16 %h0, 0x3C00;"))

    cases.append(act_kernel("ACT06", "ex2_f16x2", "ex2.approx.f16x2 (vectorized softmax)",
        "ex2.approx.f16x2 %v1, %v0;",
        ".reg .b32 %v0, %v1;",
        "mov.b32 %v0, 0x3C003C00;"))

    cases.append(act_kernel("ACT07", "ex2_bf16", "ex2.approx.ftz.bf16 (BF16 softmax)",
        "ex2.approx.ftz.bf16 %b1, %b0;",
        ".reg .b16 %b0, %b1;",
        "mov.b16 %b0, 0x3F80;"))

    cases.append(act_kernel("ACT08", "tanh_f32", "tanh.approx.f32 (sm_100 native)",
        "tanh.approx.f32 %f1, %f0;",
        ".reg .f32 %f0, %f1;",
        "mov.f32 %f0, 0f3F800000;"))

    return cases


# ===========================================================================
# Main: 生成所有测试用例
# ===========================================================================

def main():
    all_cases = []
    all_cases.extend(gen_tcgen05_cases())
    all_cases.extend(gen_tma_cases())
    all_cases.extend(gen_mbarrier_cases())
    all_cases.extend(gen_fence_cases())
    all_cases.extend(gen_int_cases())
    all_cases.extend(gen_fp_cases())
    all_cases.extend(gen_cvt_cases())
    all_cases.extend(gen_lsu_cases())
    all_cases.extend(gen_special_cases())
    all_cases.extend(gen_atomic_cases())
    # New batches for inference workload coverage
    all_cases.extend(gen_half_precision_cases())
    all_cases.extend(gen_bf16_cases())
    all_cases.extend(gen_warp_comm_cases())
    all_cases.extend(gen_bit_ops_cases())
    all_cases.extend(gen_cluster_dsmem_cases())
    all_cases.extend(gen_megakernel_ctrl_cases())
    all_cases.extend(gen_quantization_cases())
    all_cases.extend(gen_activation_cases())

    expected_paths = {
        BASE_DIR / case.batch / f"{case.case_id}_{case.mnemonic}.ptx"
        for case in all_cases
    }
    stale_paths = sorted(set(BASE_DIR.rglob("*.ptx")) - expected_paths)
    for stale_path in stale_paths:
        stale_path.unlink()
        print(f"  [removed stale] {stale_path.relative_to(BASE_DIR)}")

    print(f"Generating {len(all_cases)} PTX test cases...")
    for case in all_cases:
        fp = write_case(case)
        print(f"  [{case.batch}] {case.case_id}: {fp.name}")

    print(f"\nDone. Total: {len(all_cases)} files generated.")
    print(f"Output directory: {BASE_DIR}")


if __name__ == "__main__":
    main()

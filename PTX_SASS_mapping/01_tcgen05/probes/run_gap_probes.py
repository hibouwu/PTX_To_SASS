#!/usr/bin/env python3
"""复现《对抗式审查_实验设计缺口》引用的全部探针。

每个探针生成 PTX、以 ptxas -O3 编译、以 nvdisasm -hex -c 反汇编，并把
PTX/反汇编文本与关键观测值写入 results/。summary.json 记录工具版本、
每个产物的 SHA-256 和逐探针观测，供审查文档引用与后续机器复核。

观测值只记录原始事实（指令文本、word0/word1、计数），不在此处做解释。
字段解释（wait 掩码、屏障索引等）属于 tools/decode_ctrl.py 的职责，且
其字段布局在 sm_110a 上仍是待复核假设。

用法：
    python3 run_gap_probes.py [-o results]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ARCH = "sm_110a"
HEADER = ".version 9.0\n.target sm_110a\n.address_size 64\n"

INSN_RE = re.compile(
    r"^\s*/\*([0-9a-f]{4})\*/\s+(.*?);\s*/\* (0x[0-9a-f]{16}) \*/\s*$"
)
CTRL_RE = re.compile(r"^\s*/\* (0x[0-9a-f]{16}) \*/\s*$")


def tool(name: str) -> str:
    return shutil.which(name) or f"/usr/local/cuda/bin/{name}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def compile_and_disasm(name: str, body: str, outdir: Path) -> dict:
    """编译一个探针 kernel，返回 {指令文本, word0, word1} 列表与产物路径。"""
    ptx = outdir / f"{name}.ptx"
    cubin = outdir / f"{name}.cubin"
    disasm = outdir / f"{name}.disasm.txt"
    ptx.write_text(HEADER + body, encoding="utf-8")

    result = run([tool("ptxas"), f"-arch={ARCH}", "-O3", "-o", str(cubin), str(ptx)])
    if result.returncode != 0:
        return {"name": name, "compile": "reject",
                "diagnostic": result.stderr.strip().splitlines()[:3],
                "artifacts": {"ptx": ptx.name, "ptx_sha256": sha256(ptx)}}

    text = run([tool("nvdisasm"), "-hex", "-c", str(cubin)]).stdout
    disasm.write_text(text, encoding="utf-8")

    insns, pending = [], None
    for line in text.splitlines():
        im = INSN_RE.match(line)
        if im:
            pending = {"offset": im.group(1), "text": im.group(2).strip(),
                       "word0": im.group(3)}
            continue
        cm = CTRL_RE.match(line)
        if cm and pending is not None:
            pending["word1"] = cm.group(1)
            insns.append(pending)
            pending = None
    return {
        "name": name, "compile": "accept", "instructions": insns,
        "artifacts": {
            "ptx": ptx.name, "ptx_sha256": sha256(ptx),
            "cubin": cubin.name, "cubin_sha256": sha256(cubin),
            "disasm": disasm.name, "disasm_sha256": sha256(disasm),
        },
    }


def pick(insns, pattern):
    return [i for i in insns if re.search(pattern, i["text"])]


# ---------------------------------------------------------------- 探针定义

def probe_async_depth(outdir: Path) -> dict:
    """P0-1：同一 semantic form 的 LDTM，在不同异步深度下的 word 1 高位。"""
    cases = {}
    for n in (1, 2, 4, 6, 9):
        addr = "\n".join(f"    add.s32 %t{i},%taddr,{i*64};" for i in range(n))
        lds = "\n".join(
            f"    tcgen05.ld.sync.aligned.16x64b.x1.b32 {{%r{i}}},[%t{i}];"
            for i in range(n))
        acc = "\n".join(f"    xor.b32 %s,%s,%r{i};" for i in range(n))
        body = f""".visible .entry k(.param .u32 p_t,.param .u64 p_o)
.reqntid 32
{{
    .reg .b32 %r<{n}>,%t<{n}>,%taddr,%s; .reg .b64 %o;
    ld.param.b32 %taddr,[p_t]; ld.param.b64 %o,[p_o];
{addr}
{lds}
    tcgen05.wait::ld.sync.aligned;
    mov.b32 %s,0;
{acc}
    st.global.b32 [%o],%s;
    ret;
}}
"""
        report = compile_and_disasm(f"async_depth_{n}", body, outdir)
        report["observation"] = {
            "ldtm_word1": [i["word1"] for i in pick(report.get("instructions", []), r"^LDTM")],
            "stg_word1": [i["word1"] for i in pick(report.get("instructions", []), r"^STG")],
        }
        cases[str(n)] = report
    return {"probe": "async_depth", "claim_ref": "P0-1", "cases": cases}


MMA_LINE = ("    tcgen05.mma.cta_group::1.kind::f16 [%d], %da, %db, %idesc,"
            " {%m0,%m1,%m2,%m3}, %en;\n")


def _mma_body(idesc_line: str, reqntid: str) -> str:
    directive = f".reqntid {reqntid}\n" if reqntid else ""
    return f""".visible .entry k(.param .u32 p_d, .param .u64 p_da, .param .u64 p_db, .param .u32 p_idesc, .param .u32 p_en)
{directive}{{
    .reg .b32 %d,%idesc,%enu; .reg .b64 %da,%db; .reg .pred %en; .reg .b32 %m<4>;
    ld.param.b32 %d,[p_d]; ld.param.b64 %da,[p_da]; ld.param.b64 %db,[p_db];
    {idesc_line}
    ld.param.b32 %enu,[p_en];
    setp.ne.u32 %en,%enu,0;
    mov.b32 %m0,0; mov.b32 %m1,0; mov.b32 %m2,0; mov.b32 %m3,0;
{MMA_LINE}    ret;
}}
"""


def probe_template_idesc(outdir: Path) -> dict:
    """P1-1：idesc 来自参数与来自编译期常量，核心指令操作数文本对比。"""
    cases = {}
    for name, line in (("param", "ld.param.b32 %idesc,[p_idesc];"),
                       ("const", "mov.b32 %idesc, 0x1234abcd;")):
        report = compile_and_disasm(f"idesc_{name}", _mma_body(line, "32"), outdir)
        mma = pick(report.get("instructions", []), r"^UTCHMMA")
        report["observation"] = {"utchmma": mma}
        cases[name] = report
    return {"probe": "template_idesc", "claim_ref": "P1-1", "cases": cases}


def probe_reqntid(outdir: Path) -> dict:
    """辅助：.reqntid 取 32/128/省略时核心 MMA 是否变化。"""
    cases = {}
    for name, req in (("t32", "32"), ("t128", "128"), ("none", "")):
        report = compile_and_disasm(
            f"reqntid_{name}",
            _mma_body("ld.param.b32 %idesc,[p_idesc];", req), outdir)
        report["observation"] = {
            "utchmma": pick(report.get("instructions", []), r"^UTCHMMA")}
        cases[name] = report
    return {"probe": "reqntid", "claim_ref": "对照(已排除项)", "cases": cases}


def probe_ur_reuse(outdir: Path) -> dict:
    """P1-2：12 条各带独立描述符的 MMA，UR 槽位与 LDCU 重装载计数。"""
    n = 12
    params = "".join(
        f".param .u64 p_da{i}, .param .u64 p_db{i}, .param .u32 p_d{i}, "
        for i in range(n))
    lds = "\n".join(
        f"    ld.param.b64 %da{i},[p_da{i}]; ld.param.b64 %db{i},[p_db{i}];"
        f" ld.param.b32 %dd{i},[p_d{i}];" for i in range(n))
    mmas = "\n".join(
        f"    tcgen05.mma.cta_group::1.kind::f16 [%dd{i}], %da{i}, %db{i},"
        f" %idesc, {{%m0,%m1,%m2,%m3}}, %en;" for i in range(n))
    body = f""".visible .entry k({params}.param .u32 p_idesc, .param .u32 p_en)
.reqntid 32
{{
    .reg .b32 %idesc,%enu; .reg .pred %en; .reg .b32 %m<4>;
    .reg .b64 %da<{n}>,%db<{n}>; .reg .b32 %dd<{n}>;
{lds}
    ld.param.b32 %idesc,[p_idesc]; ld.param.b32 %enu,[p_en];
    setp.ne.u32 %en,%enu,0;
    mov.b32 %m0,0; mov.b32 %m1,0; mov.b32 %m2,0; mov.b32 %m3,0;
{mmas}
    ret;
}}
"""
    report = compile_and_disasm("ur_reuse_12mma", body, outdir)
    insns = report.get("instructions", [])
    urs = sorted({int(m) for i in insns
                  for m in re.findall(r"\bUR(\d+)\b", i["text"])})
    report["observation"] = {
        "utchmma_texts": sorted({i["text"] for i in pick(insns, r"^UTCHMMA")}),
        "ldcu_count": len(pick(insns, r"^LDCU")),
        "max_ur": max(urs) if urs else None,
    }
    return {"probe": "ur_reuse", "claim_ref": "P1-2(待验证假设)", "cases": {"12mma": report}}


def probe_gpr_pressure(outdir: Path) -> dict:
    """P1-3：200 个跨 MMA 活跃值下的 LDL/STL 计数与最大 GPR。"""
    n = 200
    mk = "\n".join(f"    mul.lo.s32 %v{i}, %seed, {i*7+1};" for i in range(n))
    use = "\n".join(f"    xor.b32 %sink, %sink, %v{i};" for i in range(n))
    body = f""".visible .entry k(.param .u32 p_d, .param .u64 p_da, .param .u64 p_db, .param .u32 p_idesc, .param .u32 p_en, .param .u64 p_out)
.reqntid 32
{{
    .reg .b32 %d,%idesc,%enu,%seed,%sink; .reg .b64 %da,%db,%out; .reg .pred %en; .reg .b32 %m<4>;
    .reg .b32 %v<{n}>;
    ld.param.b32 %d,[p_d]; ld.param.b64 %da,[p_da]; ld.param.b64 %db,[p_db];
    ld.param.b32 %idesc,[p_idesc]; ld.param.b32 %enu,[p_en]; ld.param.b64 %out,[p_out];
    mov.b32 %seed, %tid.x;
{mk}
    setp.ne.u32 %en,%enu,0;
    mov.b32 %m0,0; mov.b32 %m1,0; mov.b32 %m2,0; mov.b32 %m3,0;
{MMA_LINE}    mov.b32 %sink,0;
{use}
    st.global.b32 [%out], %sink;
    ret;
}}
"""
    report = compile_and_disasm("gpr_pressure_200", body, outdir)
    insns = report.get("instructions", [])
    gprs = sorted({int(m) for i in insns
                   for m in re.findall(r"\bR(\d+)\b", i["text"])})
    report["observation"] = {
        "ldl_stl_count": len(pick(insns, r"^(LDL|STL)\b")),
        "max_gpr": max(gprs) if gprs else None,
        "utchmma_texts": [i["text"] for i in pick(insns, r"^UTCHMMA")],
    }
    return {"probe": "gpr_pressure", "claim_ref": "P1-3", "cases": {"live200": report}}


def probe_splice(outdir: Path) -> dict:
    """P0-3：同一段代码单独编译与拼接编译时目标指令 word 1 的差异。"""
    def seg(i: int) -> str:
        return (f"    add.s32 %t{i},%taddr,{i*64};\n"
                f"    tcgen05.ld.sync.aligned.16x64b.x1.b32 {{%r{i}}},[%t{i}];\n"
                f"    tcgen05.wait::ld.sync.aligned;\n"
                f"    xor.b32 %s{i},%r{i},{i+1};\n"
                f"    add.s64 %o{i},%out,{i*4};\n"
                f"    st.global.b32 [%o{i}],%s{i};\n")

    def kernel(segments) -> str:
        return f""".visible .entry k(.param .u32 p_t, .param .u64 p_out)
.reqntid 32
{{
    .reg .b32 %r<8>,%t<8>,%s<8>,%taddr; .reg .b64 %out,%o<8>;
    ld.param.b32 %taddr,[p_t]; ld.param.b64 %out,[p_out];
{''.join(seg(i) for i in segments)}    ret;
}}
"""
    cases = {}
    for name, segments in (("segA", [0]), ("segB", [1]), ("segAB", [0, 1])):
        report = compile_and_disasm(f"splice_{name}", kernel(segments), outdir)
        report["observation"] = {
            "ldtm_word1": [i["word1"] for i in pick(report.get("instructions", []), r"^LDTM")],
            "stg_word1": [i["word1"] for i in pick(report.get("instructions", []), r"^STG")],
        }
        cases[name] = report
    return {"probe": "splice", "claim_ref": "P0-3", "cases": cases}


# ---------------------------------------------------------------- 主流程

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--outdir", type=Path,
                        default=Path(__file__).resolve().parent / "results")
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    versions = {
        "ptxas": run([tool("ptxas"), "--version"]).stdout.strip().splitlines()[-1],
        "nvdisasm": run([tool("nvdisasm"), "--version"]).stdout.strip().splitlines()[-1],
        "arch": ARCH,
    }
    probes = [
        probe_async_depth(args.outdir),
        probe_template_idesc(args.outdir),
        probe_reqntid(args.outdir),
        probe_ur_reuse(args.outdir),
        probe_gpr_pressure(args.outdir),
        probe_splice(args.outdir),
    ]
    summary = {"schema_version": "tcgen05_gap_probes_v1",
               "environment": versions, "probes": probes}
    out = args.outdir / "summary.json"
    out.write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    print(f"探针 {len(probes)} 组，产物目录 {args.outdir}")
    print(f"summary sha256={hashlib.sha256(out.read_bytes()).hexdigest()[:16]}")
    for p in probes:
        states = {c.get("compile") for c in p["cases"].values()}
        print(f"  {p['probe']:<16} cases={len(p['cases'])} compile={sorted(states)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

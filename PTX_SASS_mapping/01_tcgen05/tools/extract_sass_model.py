#!/usr/bin/env python3
"""从 DocumentSASS 的 nvdisasm memcpy 截获流中提取 SASS 调度模型。

替代上游 funnel.py：CUDA 13.0 起 `ARCHITECTURE` 标记已不存在，
且 memcpy 流是交错的，无法按 src 指针整块重组。本脚本改为按行特征过滤。

用法：
    extract_sass_model.py <intercept.txt> [-o 输出目录]
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
import hashlib
from pathlib import Path
import re
import sys


DELIMITER_RE = re.compile(r"^<0x[0-9a-f]+ 0x[0-9a-f]+ \d+>$")
TABLE_RE = re.compile(r"^TABLE_(TRUE|ANTI|OUTPUT)\(([A-Z_0-9]+)\)")
LETTER_RE = re.compile(r"[A-Za-z]")

# 顶层小节标记。ELF/cubin 元数据标记（EIATTR_*、SHT_* 等）不在此列。
SECTION_MARKERS = (
    "OPERATION SETS",
    "OPERATION PIPELINE RESOURCES",
    "HARD RESOURCE",
    "RESOURCE",
    "CONNECTOR NAMES",
    "CONNECTOR NAME",
    "CONNECTOR SETS",
    "CONNECTOR CONDITIONS",
)

# 本项目关心的指令。用于生成 tcgen05 专用摘要。
TCGEN05_OPS = (
    "UTCHMMA", "UTCIMMA", "UTCQMMA", "UTCOMMA",
    "UTCCP", "UTCBAR", "UTCSHIFT", "UTCATOMSWS",
    "LDTM", "STTM", "UVIRTCOUNT",
)


def is_content(line: str) -> bool:
    """判断一行是否属于模型文本而非 memcpy 噪声。"""
    if DELIMITER_RE.match(line):
        return False
    stripped = line.strip()
    if not stripped:
        return False
    if stripped in SECTION_MARKERS or TABLE_RE.match(stripped):
        return True
    if len(LETTER_RE.findall(stripped)) < 3:
        return False
    # 噪声多为短片段；模型文本是长结构化行。
    if len(stripped) < 20:
        return False
    # 非 ASCII 可打印字符占比过高的判为噪声。
    printable = sum(1 for ch in stripped if 32 <= ord(ch) < 127)
    return printable / len(stripped) > 0.9


def load(path: Path) -> list[str]:
    raw = path.read_text(encoding="ascii", errors="replace")
    return [line for line in raw.splitlines() if is_content(line)]


def split_sections(lines: list[str]) -> "OrderedDict[str, list[str]]":
    """按顶层标记切段。同名标记多次出现时追加编号。"""
    sections: OrderedDict[str, list[str]] = OrderedDict()
    seen: dict[str, int] = {}
    current = "PREAMBLE"
    sections[current] = []
    for line in lines:
        stripped = line.strip()
        marker = stripped if stripped in SECTION_MARKERS else None
        table = TABLE_RE.match(stripped)
        if marker or table:
            name = marker if marker else table.group(0)
            seen[name] = seen.get(name, 0) + 1
            current = name if seen[name] == 1 else f"{name}#{seen[name]}"
            sections.setdefault(current, [])
        sections[current].append(line)
    return sections


def collect_operation_sets(sections) -> "OrderedDict[str, str]":
    """从 OPERATION SETS 段解析 `名字 = {成员}` 定义。"""
    defs: OrderedDict[str, str] = OrderedDict()
    pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.+?);?\s*$")
    for name, body in sections.items():
        if not name.startswith("OPERATION SETS"):
            continue
        for line in body:
            match = pattern.match(line)
            if match:
                defs.setdefault(match.group(1), match.group(2))
    return defs


def tcgen05_summary(op_sets, sections) -> list[str]:
    out = ["# tcgen05 相关操作集", ""]
    for name, members in op_sets.items():
        if any(op in members for op in TCGEN05_OPS):
            out.append(f"{name} = {members}")
    out += ["", "# 含 tcgen05 指令的延迟表行", ""]
    for name, body in sections.items():
        if not name.startswith("TABLE_"):
            continue
        hits = [
            line.rstrip()
            for line in body
            if any(op in line for op in TCGEN05_OPS)
            or re.search(r"\b(OP_TMA_TC|LDTM_STTM_OP|OP_SWS|ATOMSWS_OP)\b", line)
        ]
        if hits:
            out.append(f"## {name}")
            out.extend(hits)
            out.append("")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("intercept", type=Path, help="LD_PRELOAD 截获的原始文本")
    parser.add_argument("-o", "--outdir", type=Path, default=Path("sass_model"))
    args = parser.parse_args()

    if not args.intercept.is_file():
        print(f"找不到输入文件：{args.intercept}", file=sys.stderr)
        return 1

    lines = load(args.intercept)
    if not lines:
        print("过滤后没有内容，检查截获是否成功。", file=sys.stderr)
        return 1

    sections = split_sections(lines)
    op_sets = collect_operation_sets(sections)

    args.outdir.mkdir(parents=True, exist_ok=True)
    for name, body in sections.items():
        safe = re.sub(r"[^A-Za-z0-9_#()-]+", "_", name).strip("_")
        (args.outdir / f"{safe}.txt").write_text("\n".join(body) + "\n", encoding="utf-8")

    (args.outdir / "operation_sets.txt").write_text(
        "\n".join(f"{k} = {v}" for k, v in op_sets.items()) + "\n", encoding="utf-8"
    )
    (args.outdir / "tcgen05_summary.txt").write_text(
        "\n".join(tcgen05_summary(op_sets, sections)) + "\n", encoding="utf-8"
    )

    digest = hashlib.sha256(args.intercept.read_bytes()).hexdigest()
    tables = [n for n in sections if n.startswith("TABLE_")]
    print(f"输入 {args.intercept}  sha256={digest[:16]}")
    print(f"内容行 {len(lines)}  小节 {len(sections)}  操作集定义 {len(op_sets)}")
    print(f"延迟表 {len(tables)}: {', '.join(tables[:8])}{' ...' if len(tables) > 8 else ''}")
    print(f"输出目录 {args.outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

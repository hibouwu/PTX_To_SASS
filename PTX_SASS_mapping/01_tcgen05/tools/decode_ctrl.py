#!/usr/bin/env python3
"""解码 cubin 中每条 SASS 指令的调度控制位。

控制位位于 128-bit 指令的第二个 64-bit 字高位，nvdisasm 的文本输出不显示。
字段位置沿用 Volta 系公开布局；已在 sm_110a 上通过生产者/消费者配对自洽验证，
但仍应在目标机器上用已知依赖形态复核（见 --verify）。

用法：
    decode_ctrl.py <cubin> [--kernel 名字] [--verify] [--json 输出.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


# word1 内的字段位置。索引 7 表示不使用该屏障。
FIELDS = {
    "reuse": (61, 58),
    "wait": (57, 52),
    "read_barrier": (51, 49),
    "write_barrier": (48, 46),
    "yield": (45, 45),
    "stall": (44, 41),
}
NO_BARRIER = 7

INSN_RE = re.compile(
    r"^\s*/\*([0-9a-f]{4})\*/\s+(.*?);\s*/\* (0x[0-9a-f]{16}) \*/\s*$"
)
CTRL_RE = re.compile(r"^\s*/\* (0x[0-9a-f]{16}) \*/\s*$")
KERNEL_RE = re.compile(r"^\s*\.text\.(\S+):\s*$")
# 写入寄存器的指令，其目的寄存器是第一个操作数。
# 助记符的修饰符含小写与下划线，例如 LDTM.16dp64bit、UTCCP.T.S.2x64dp128bit_lw02_lw13。
DEST_RE = re.compile(r"^\s*(?:@!?U?P\w+\s+)?[A-Z][A-Za-z0-9._:]*\s+(U?R\d+|U?P\d+)")
SRC_RE = re.compile(r"\b(UR\d+|R\d+|UP\d+|P\d+)\b")


def extract(word1: int) -> dict:
    out = {}
    for name, (hi, lo) in FIELDS.items():
        out[name] = (word1 >> lo) & ((1 << (hi - lo + 1)) - 1)
    return out


def barrier_name(index: int) -> str | None:
    return None if index == NO_BARRIER else f"SB{index}"


def wait_list(mask: int) -> list[str]:
    return [f"SB{i}" for i in range(6) if mask & (1 << i)]


def disassemble(cubin: Path) -> str:
    exe = shutil.which("nvdisasm") or "/usr/local/cuda/bin/nvdisasm"
    result = subprocess.run(
        [exe, "-hex", "-c", str(cubin)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"nvdisasm 失败：{result.stderr.strip()[:200]}")
    return result.stdout


def parse(listing: str) -> list[dict]:
    """把反汇编输出配对成 (指令文本, word0, word1)。"""
    insns: list[dict] = []
    kernel = "?"
    pending = None
    for line in listing.splitlines():
        km = KERNEL_RE.match(line)
        if km:
            kernel = km.group(1)
            continue
        im = INSN_RE.match(line)
        if im:
            pending = {
                "kernel": kernel,
                "offset": im.group(1),
                "text": im.group(2).strip(),
                "word0": int(im.group(3), 16),
            }
            continue
        cm = CTRL_RE.match(line)
        if cm and pending is not None:
            pending["word1"] = int(cm.group(1), 16)
            pending.update(extract(pending["word1"]))
            insns.append(pending)
            pending = None
    return insns


def written_registers(text: str) -> set[str]:
    """目的寄存器集合。`.64`/`.128` 形态会连带写入后续编号的寄存器。"""
    match = DEST_RE.match(text)
    if not match:
        return set()
    dest = match.group(1)
    regs = {dest}
    width = 2 if ".64" in text else (4 if ".128" in text else 1)
    prefix = re.match(r"^(U?[RP])(\d+)$", dest)
    if prefix and width > 1:
        base = int(prefix.group(2))
        regs |= {f"{prefix.group(1)}{base + k}" for k in range(width)}
    return regs


def classify_waits(insns: list[dict]) -> tuple[list[dict], list[str]]:
    """把每个等待归类，并找出真正的异常。

    分类：
      data     消费者引用了生产者写入的寄存器，即数据依赖边。
      overlap  两条指令写入集合相交，属于写后写或写后读顺序约束。
      reclaim  两者无寄存器关联。编译器为腾出屏障索引而插入的回收等待。
      未设置    等待了一个此前没有指令设置的屏障，属于真正的异常。

    reclaim 不是错误，但会在"边包含"比对中表现为多余的边，必须单独剔除。
    """
    edges: list[dict] = []
    errors: list[str] = []
    setter: dict[str, dict] = {}

    for insn in insns:
        # 读写同一寄存器是合法的，因此不从引用集合中剔除目的寄存器。
        referenced = set(SRC_RE.findall(insn["text"]))
        writes = written_registers(insn["text"])

        for barrier in wait_list(insn["wait"]):
            producer = setter.pop(barrier, None)
            if producer is None:
                errors.append(
                    f"{insn['offset']} {insn['text'][:40]!r} 等待 {barrier}，"
                    f"但此前没有指令设置该屏障"
                )
                continue
            produced = producer["writes"]
            if produced & referenced:
                kind = "data"
            elif produced & writes:
                kind = "overlap"
            else:
                kind = "reclaim"
            edges.append({
                "barrier": barrier,
                "kind": kind,
                "producer": producer["offset"],
                "consumer": insn["offset"],
                "producer_text": producer["text"][:48],
                "consumer_text": insn["text"][:48],
            })

        wb = barrier_name(insn["write_barrier"])
        if wb:
            setter[wb] = {"offset": insn["offset"], "writes": writes, "text": insn["text"]}
        rb = barrier_name(insn["read_barrier"])
        if rb:
            # 读屏障保护的是源操作数，消费者是后续覆盖这些寄存器的指令。
            setter.setdefault(
                rb, {"offset": insn["offset"], "writes": referenced, "text": insn["text"]}
            )
    return edges, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cubin", type=Path)
    parser.add_argument("--kernel", help="只输出该 kernel")
    parser.add_argument("--verify", action="store_true", help="做生产者/消费者自洽检查")
    parser.add_argument("--json", type=Path, help="同时写出 JSON")
    args = parser.parse_args()

    if not args.cubin.is_file():
        print(f"找不到 {args.cubin}", file=sys.stderr)
        return 1

    insns = parse(disassemble(args.cubin))
    if args.kernel:
        insns = [i for i in insns if i["kernel"] == args.kernel]
    if not insns:
        print("没有解析到指令。确认输入是 cubin 且 nvdisasm 支持该架构。", file=sys.stderr)
        return 1

    print(f"{'偏移':<6}{'指令':<52}{'wait':<14}{'写屏障':<8}{'读屏障':<8}{'yld':<5}{'stall'}")
    for insn in insns:
        waits = ",".join(wait_list(insn["wait"])) or "-"
        print(
            f"{insn['offset']:<6}{insn['text'][:50]:<52}{waits:<14}"
            f"{barrier_name(insn['write_barrier']) or '-':<8}"
            f"{barrier_name(insn['read_barrier']) or '-':<8}"
            f"{insn['yield']:<5}{insn['stall']}"
        )

    edges, errors = classify_waits(insns)

    if args.json:
        payload = {"instructions": insns, "edges": edges, "errors": errors}
        args.json.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"\n已写出 {args.json}")

    if args.verify:
        counts = {k: sum(1 for e in edges if e["kind"] == k) for k in ("data", "overlap", "reclaim")}
        print()
        print(f"依赖边 {len(edges)}：数据 {counts['data']}、"
              f"写重叠 {counts['overlap']}、屏障回收 {counts['reclaim']}")
        for edge in edges:
            if edge["kind"] == "reclaim":
                print(f"  回收 {edge['barrier']}: {edge['producer']} -> {edge['consumer']}"
                      f"  {edge['consumer_text']!r} 与生产者无寄存器关联")
        if errors:
            print(f"\n异常 {len(errors)} 处：")
            for item in errors:
                print("  " + item)
            print("\n若同类异常成片出现，应怀疑字段位置在该架构上有偏移。")
        else:
            print("\n无异常：所有等待都能追溯到设置该屏障的生产者。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

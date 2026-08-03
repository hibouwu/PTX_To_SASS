#!/usr/bin/env python3
"""Generate CTX.protocol and complete effect-slice PTX cases for Thor."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from suite_utils import reset_owned_directory
from validate_generated import validate_directory


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ProtocolCase:
    label: str
    layer: str
    coordinates: dict
    declarations: tuple[str, ...]
    parameters: tuple[str, ...]
    registers: tuple[str, ...]
    body: tuple[str, ...]
    entry_directives: tuple[str, ...] = ()


def module_source(case: ProtocolCase) -> str:
    parameter_text = ",\n".join(f"    {item}" for item in case.parameters)
    lines = [
        ".version 9.0",
        ".target sm_110a",
        ".address_size 64",
        f'.file 1 "{case.label}.ptx"',
        "",
        *case.declarations,
        "",
        f"// LAYER {case.layer}",
        "// COORDINATES "
        + json.dumps(case.coordinates, sort_keys=True, separators=(",", ":")),
        f".visible .entry {case.label}(",
        parameter_text,
        ")",
        *[f"    {item}" for item in case.entry_directives],
        "{",
        *[f"    {item}" for item in case.registers],
        "    // EFFECT_SLICE_BEGIN",
        *[f"    {item}" if item and not item.endswith(":") else item for item in case.body],
        "    // EFFECT_SLICE_END",
        "    ret;",
        "}",
        "",
    ]
    return "\n".join(lines)


def allocation_cases() -> list[ProtocolCase]:
    cases = []
    for cta_group in (1, 2):
        for ncols in (32, 64, 128, 256, 512):
            for state_space in ("generic", "shared_cta"):
                space = "" if state_space == "generic" else ".shared::cta"
                label = f"ctx_alloc_cg{cta_group}_{ncols}_{state_space}"
                cases.append(
                    ProtocolCase(
                        label=label,
                        layer="CTX.protocol",
                        coordinates={
                            "family": "allocation_lifecycle",
                            "cta_group": cta_group,
                            "ncols": ncols,
                            "alloc_state_space": state_space,
                        },
                        declarations=(".shared .align 4 .b32 alloc_slot;",),
                        parameters=(),
                        registers=(".reg .b32 %taddr;",),
                        body=(
                            f"tcgen05.alloc.cta_group::{cta_group}.sync.aligned"
                            f"{space}.b32 [alloc_slot], {ncols};",
                            "ld.shared::cta.b32 %taddr, [alloc_slot];",
                            f"tcgen05.dealloc.cta_group::{cta_group}.sync.aligned.b32 "
                            f"%taddr, {ncols};",
                            f"tcgen05.relinquish_alloc_permit.cta_group::{cta_group}."
                            "sync.aligned;",
                        ),
                    )
                )
    return cases


def fence_cases() -> list[ProtocolCase]:
    return [
        ProtocolCase(
            label=f"ctx_fence_{position}",
            layer="CTX.protocol",
            coordinates={"family": "tcgen05_fence", "position": position},
            declarations=(),
            parameters=(),
            registers=(),
            body=(f"tcgen05.fence::{position}_thread_sync;",),
        )
        for position in ("before", "after")
    ]


def proxy_fence_cases() -> list[ProtocolCase]:
    return [
        ProtocolCase(
            label=f"ctx_proxy_fence_{space}",
            layer="CTX.protocol",
            coordinates={
                "family": "async_proxy_fence",
                "state_space": space,
                "direction": "bidirectional_generic_async",
            },
            declarations=(),
            parameters=(),
            registers=(),
            body=(
                "fence.proxy.async"
                + (";" if space == "all" else f".{space.replace('_', '::')};"),
            ),
        )
        for space in ("all", "shared_cta", "shared_cluster")
    ]


def commit_cases() -> list[ProtocolCase]:
    cases = []
    for cta_group in (1, 2):
        cases.append(
            ProtocolCase(
                label=f"ctx_commit_cg{cta_group}_generic",
                layer="CTX.protocol",
                coordinates={
                    "family": "commit",
                    "cta_group": cta_group,
                    "state_space": "generic",
                    "multicast": False,
                },
                declarations=(),
                parameters=(".param .u64 p_mbar",),
                registers=(".reg .b64 %mbar;",),
                body=(
                    "ld.param.b64 %mbar, [p_mbar];",
                    f"tcgen05.commit.cta_group::{cta_group}."
                    "mbarrier::arrive::one.b64 [%mbar];",
                ),
            )
        )
        cases.append(
            ProtocolCase(
                label=f"ctx_commit_cg{cta_group}_shared_cluster",
                layer="CTX.protocol",
                coordinates={
                    "family": "commit",
                    "cta_group": cta_group,
                    "state_space": "shared_cluster",
                    "multicast": False,
                },
                declarations=(".shared .align 8 .b64 mbar_obj;",),
                parameters=(),
                registers=(),
                body=(
                    f"tcgen05.commit.cta_group::{cta_group}."
                    "mbarrier::arrive::one.shared::cluster.b64 [mbar_obj];",
                ),
            )
        )
        cases.append(
            ProtocolCase(
                label=f"ctx_commit_cg{cta_group}_multicast",
                layer="CTX.protocol",
                coordinates={
                    "family": "commit",
                    "cta_group": cta_group,
                    "state_space": "shared_cluster",
                    "multicast": True,
                },
                declarations=(".shared .align 8 .b64 mbar_obj;",),
                parameters=(".param .u16 p_cta_mask",),
                registers=(".reg .b16 %cta_mask;",),
                body=(
                    "ld.param.b16 %cta_mask, [p_cta_mask];",
                    f"tcgen05.commit.cta_group::{cta_group}."
                    "mbarrier::arrive::one.shared::cluster.multicast::cluster.b64 "
                    "[mbar_obj], %cta_mask;",
                ),
            )
        )
    return cases


def mbarrier_cases() -> list[ProtocolCase]:
    cases = []
    for scope in ("cta", "cluster"):
        for arrive_sem in ("relaxed", "release"):
            for wait_sem in ("relaxed", "acquire"):
                semantics = f"{arrive_sem}_{wait_sem}"
                label = f"ctx_mbarrier_{scope}_{semantics}"
                cases.append(
                    ProtocolCase(
                        label=label,
                        layer="CTX.protocol",
                        coordinates={
                            "family": "mbarrier_lifecycle",
                            "scope": scope,
                            "arrive_semantics": arrive_sem,
                            "wait_semantics": wait_sem,
                            "state_space": "shared_cta",
                        },
                        declarations=(".shared .align 8 .b64 mbar_obj;",),
                        parameters=(),
                        registers=(".reg .pred %complete;",),
                        body=(
                            "mbarrier.init.shared::cta.b64 [mbar_obj], 1;",
                            "bar.cta.sync 0;",
                            f"mbarrier.arrive.{arrive_sem}.{scope}.shared::cta.b64 "
                            "_, [mbar_obj];",
                            f"mbarrier.try_wait.parity.{wait_sem}.{scope}."
                            "shared::cta.b64 %complete, [mbar_obj], 0;",
                            "bar.cta.sync 0;",
                            "mbarrier.inval.shared::cta.b64 [mbar_obj];",
                        ),
                    )
                )
    return cases


def ld_st_wait_cases() -> list[ProtocolCase]:
    result = []
    for operation in ("ld", "st"):
        instruction = (
            "tcgen05.ld.sync.aligned.32x32b.x2.b32 {%r0, %r1}, [%taddr];"
            if operation == "ld"
            else "tcgen05.st.sync.aligned.32x32b.x2.b32 [%taddr], {%r0, %r1};"
        )
        parameters = [
            ".param .u32 p_taddr",
            ".param .u32 p_r0",
            ".param .u32 p_r1",
        ]
        registers = [".reg .b32 %taddr, %r0, %r1;"]
        body = [
            "ld.param.b32 %taddr, [p_taddr];",
            "ld.param.b32 %r0, [p_r0];",
            "ld.param.b32 %r1, [p_r1];",
            instruction,
            f"tcgen05.wait::{operation}.sync.aligned;",
        ]
        if operation == "ld":
            parameters.append(".param .u64 p_out")
            registers.append(".reg .b64 %out;")
            body.extend(
                (
                    "ld.param.b64 %out, [p_out];",
                    "st.global.v2.b32 [%out], {%r0, %r1};",
                )
            )
        result.append(
            ProtocolCase(
                label=f"ctx_{operation}_wait",
                layer="CTX.protocol",
                coordinates={
                    "family": "tmem_io_completion",
                    "operation": operation,
                    "completion": f"wait::{operation}",
                },
                declarations=(),
                parameters=tuple(parameters),
                registers=tuple(registers),
                body=tuple(body),
            )
        )
    return result


def effect_slice_case(
    cta_group: int, *, include_store: bool, explicit_fences: bool
) -> ProtocolCase:
    profile = (
        ("st_wait_" if include_store else "")
        + ("explicit_fences" if explicit_fences else "commit_ordering")
    )
    mask_count = 4 if cta_group == 1 else 8
    mask_decl = f".reg .b32 %mask<{mask_count}>;"
    rank_setup = (
        [
            "mov.u32 %rank, %cluster_ctarank;",
            "and.b32 %rank_parity, %rank, 1;",
            "setp.eq.u32 %even_cta, %rank_parity, 0;",
            "and.pred %issuer, %lane_zero, %even_cta;",
            "mad.wide.u32 %out_cta, %rank, 8, %out;",
            "mov.b16 %cta_mask, 0x3;",
        ]
        if cta_group == 2
        else ["mov.pred %issuer, %lane_zero;", "mov.b64 %out_cta, %out;"]
    )
    body = [
        "mov.u32 %lane, %laneid;",
        "setp.eq.u32 %lane_zero, %lane, 0;",
        f"tcgen05.alloc.cta_group::{cta_group}.sync.aligned."
        "shared::cta.b32 [alloc_slot], 32;",
        "bar.cta.sync 0;",
        "ld.shared::cta.b32 %taddr, [alloc_slot];",
        "ld.param.b64 %desc_a, [p_desc_a];",
        "ld.param.b64 %desc_b, [p_desc_b];",
        "ld.param.b32 %idesc, [p_idesc];",
        "ld.param.b64 %out, [p_out];",
        *rank_setup,
        "setp.eq.u32 %enable, 0, 1;",
        "mov.b32 %io0, 0;",
        "mov.b32 %io1, 0;",
    ]
    body.extend(f"mov.b32 %mask{index}, 0;" for index in range(mask_count))
    body.extend(
        (
            "@%lane_zero mbarrier.init.shared::cta.b64 [mbar_obj], 1;",
            "bar.cta.sync 0;",
            "fence.proxy.async;",
        )
    )
    if include_store:
        body.extend(
            (
                "tcgen05.st.sync.aligned.32x32b.x2.b32 "
                "[%taddr], {%io0, %io1};",
                "tcgen05.wait::st.sync.aligned;",
            )
        )
    if explicit_fences:
        body.append("tcgen05.fence::after_thread_sync;")
    masks = "{" + ", ".join(f"%mask{i}" for i in range(mask_count)) + "}"
    body.extend(
        (
            f"@%issuer tcgen05.mma.cta_group::{cta_group}.kind::f16 "
            f"[%taddr], %desc_a, %desc_b, %idesc, {masks}, %enable;",
            (
                "@%issuer tcgen05.commit.cta_group::2.mbarrier::arrive::one."
                "shared::cluster.multicast::cluster.b64 [mbar_obj], %cta_mask;"
                if cta_group == 2
                else "@%issuer tcgen05.commit.cta_group::1.mbarrier::arrive::one."
                "shared::cluster.b64 [mbar_obj];"
            ),
            "EFFECT_WAIT:",
            "mbarrier.try_wait.parity.acquire.cluster.shared::cta.b64 "
            "%complete, [mbar_obj], 0;",
            "@!%complete bra EFFECT_WAIT;",
            "tcgen05.fence::after_thread_sync;",
            "tcgen05.ld.sync.aligned.32x32b.x2.b32 "
            "{%io0, %io1}, [%taddr];",
            "tcgen05.wait::ld.sync.aligned;",
            "@%lane_zero st.global.v2.b32 [%out_cta], {%io0, %io1};",
        )
    )
    if explicit_fences:
        body.append("tcgen05.fence::before_thread_sync;")
    body.extend(
        (
            "bar.cta.sync 0;",
            f"tcgen05.dealloc.cta_group::{cta_group}."
            "sync.aligned.b32 %taddr, 32;",
            f"tcgen05.relinquish_alloc_permit.cta_group::{cta_group}."
            "sync.aligned;",
            "bar.cta.sync 0;",
            "@%lane_zero mbarrier.inval.shared::cta.b64 [mbar_obj];",
        )
    )
    return ProtocolCase(
        label=f"effect_cg{cta_group}_{profile}",
        layer="effect_slice",
        coordinates={
            "family": "full_tmem_mma_lifecycle",
            "cta_group": cta_group,
            "include_store_wait": include_store,
            "explicit_fences": explicit_fences,
            "completion": "commit_mbarrier_then_ld_wait",
            "validation_scope": "STATIC_ASSEMBLY_ONLY",
        },
        declarations=(
            ".shared .align 4 .b32 alloc_slot;",
            ".shared .align 8 .b64 mbar_obj;",
        ),
        parameters=(
            ".param .u64 p_desc_a",
            ".param .u64 p_desc_b",
            ".param .u32 p_idesc",
            ".param .u64 p_out",
        ),
        registers=(
            ".reg .b32 %taddr, %idesc, %io0, %io1, %lane, %rank, %rank_parity;",
            ".reg .b64 %desc_a, %desc_b;",
            ".reg .b64 %out, %out_cta;",
            ".reg .b16 %cta_mask;",
            ".reg .pred %lane_zero, %even_cta, %issuer, %enable, %complete;",
            mask_decl,
        ),
        body=tuple(body),
        entry_directives=(
            (".reqntid 32", ".reqnctapercluster 2", ".explicitcluster")
            if cta_group == 2
            else (".reqntid 32",)
        ),
    )


def all_cases() -> list[ProtocolCase]:
    protocol = (
        allocation_cases()
        + fence_cases()
        + proxy_fence_cases()
        + commit_cases()
        + mbarrier_cases()
        + ld_st_wait_cases()
    )
    effects = [
        effect_slice_case(
            cta_group,
            include_store=include_store,
            explicit_fences=explicit_fences,
        )
        for cta_group in (1, 2)
        for include_store in (False, True)
        for explicit_fences in (False, True)
    ]
    return protocol + effects


def write_cases(output: Path) -> None:
    output = reset_owned_directory(
        output, owner="thor_tcgen05_protocol_generated", protected=(ROOT,)
    )
    cases = all_cases()
    manifest = []
    layer_counts: dict[str, int] = {}
    for case in cases:
        layer_dir = output / case.layer
        layer_dir.mkdir(exist_ok=True)
        source = module_source(case)
        source_path = layer_dir / f"{case.label}.ptx"
        source_path.write_text(source, encoding="utf-8")
        digest = hashlib.sha256(
            json.dumps(case.coordinates, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        manifest.append(
            {
                "case_label": case.label,
                "case_key_sha256": digest,
                "layer": case.layer,
                "source": str(source_path.relative_to(output)),
                "coordinates": case.coordinates,
                "validation_scope": "STATIC_ASSEMBLY_ONLY",
            }
        )
        layer_counts[case.layer] = layer_counts.get(case.layer, 0) + 1
    with (output / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for row in manifest:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    summary = {
        "schema_version": "thor_tcgen05_protocol_generator_v1",
        "ptx_isa": "9.0",
        "ptx_target": "sm_110a",
        "case_count": len(cases),
        "layer_case_counts": layer_counts,
        "validation_scope": "STATIC_ASSEMBLY_ONLY",
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    validation = validate_directory(output)
    print(
        f"generated {len(cases)} protocol/effect cases: {layer_counts}; "
        f"source validation {validation['validation_status']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "protocol_generated"
    )
    args = parser.parse_args()
    write_cases(args.output)


if __name__ == "__main__":
    main()

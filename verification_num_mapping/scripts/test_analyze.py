#!/usr/bin/env python3
"""Unit tests for conservative raw-to-core SASS cleaning."""

import unittest
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze


def ptx(instruction: str, batch: str = "test", case_id: str = "X") -> analyze.PTXInfo:
    return analyze.PTXInfo(
        filepath=Path("case.ptx"),
        batch=batch,
        case_id=case_id,
        mnemonic="case",
        target_instruction=instruction,
    )


def sass(opcode: str, operands: str = "", predicate: str = "") -> dict:
    return {
        "opcode": opcode,
        "operands": operands,
        "predicate": predicate,
        "source_line": 100,
        "raw": "",
    }


class CoreCleaningTests(unittest.TestCase):
    def test_t05_reduces_to_three_core_instructions(self):
        raw = [
            sass("WARPSYNC.ALL"),
            sass("NOP"),
            sass("IADD3", "R0, PT, PT, R0, RZ, RZ"),
            sass("MOV", "R0, R0"),
            sass("WARPSYNC.ALL"),
            sass("NOP"),
            sass("R2UR", "UR4, R0"),
            sass("LDTM.16", "dp64bit R0, tmem[UR4]"),
            sass("MOV", "R0, R0"),
        ]
        core, notes = analyze.clean_target_instructions(
            ptx("tcgen05.ld.sync.aligned.16x64b.x1.b32 {%dst0}, [%taddr];"),
            raw,
        )
        self.assertEqual(
            [item["opcode"] for item in core],
            ["WARPSYNC.ALL", "R2UR", "LDTM.16"],
        )
        self.assertIn("duplicate WARPSYNC.ALL", notes)

    def test_special_register_mov_drops_self_copy(self):
        core, _ = analyze.clean_target_instructions(
            ptx("mov.u32 %r0, %tid.x;"),
            [sass("S2R", "R0, SR_TID.X"), sass("MOV", "R0, R0")],
        )
        self.assertEqual([item["opcode"] for item in core], ["S2R"])

    def test_register_mov_preserves_one_copy_per_lane(self):
        core, _ = analyze.clean_target_instructions(
            ptx("mov.b64 %rd1, %rd0;"),
            [
                sass("MOV", "R2, R2"),
                sass("MOV", "R3, R3"),
                sass("MOV", "R2, R2"),
                sass("MOV", "R3, R3"),
            ],
        )
        self.assertEqual(len(core), 2)

    def test_ret_drops_padding_and_exit_trap(self):
        core, _ = analyze.clean_target_instructions(
            ptx("ret;"),
            [sass("EXIT"), sass("BRA", "`(.L_x_0)"), sass("NOP")],
        )
        self.assertEqual([item["opcode"] for item in core], ["EXIT"])

    def test_formatter_preserves_predicate(self):
        self.assertEqual(
            analyze.format_sass_instruction(sass("BRA", "`(.L_x_1)", "@!P0")),
            "@!P0 BRA `(.L_x_1)",
        )

    def test_o3_reordered_source_locations_are_flagged(self):
        text = """
//## File "ptx_mapping_case.ptx", line 10
/*0000*/ MOV R0, R0 ;
//## File "ptx_mapping_case.ptx", line 200
/*0010*/ LDC R2, c[0x0][0x0] ;
//## File "ptx_mapping_case.ptx", line 100
/*0020*/ FADD R0, R0, R2 ;
"""
        with tempfile.NamedTemporaryFile("w", suffix=".sass") as handle:
            handle.write(text)
            handle.flush()
            parsed = analyze.parse_sass_file(Path(handle.name), "O3")
        self.assertTrue(parsed.source_locations_interleaved)

    def test_parser_accepts_constant_and_uniform_predicates(self):
        text = """
//## File "ptx_mapping_case.ptx", line 100
/*0000*/ @!PT LDS RZ, [RZ] ;
/*0010*/ @UP0 BRA `(.L_x_0) ;
"""
        with tempfile.NamedTemporaryFile("w", suffix=".sass") as handle:
            handle.write(text)
            handle.flush()
            parsed = analyze.parse_sass_file(Path(handle.name), "O0")
        self.assertEqual(
            [item["predicate"] for item in parsed.target_instructions],
            ["@!PT", "@UP0"],
        )

    def test_parser_fails_closed_on_unknown_instruction_syntax(self):
        text = """
//## File "ptx_mapping_case.ptx", line 100
/*0000*/ @Q0 LDS RZ, [RZ] ;
"""
        with tempfile.NamedTemporaryFile("w", suffix=".sass") as handle:
            handle.write(text)
            handle.flush()
            with self.assertRaisesRegex(ValueError, "Unparsed SASS"):
                analyze.parse_sass_file(Path(handle.name), "O0")

    def test_lsu_audit_keeps_only_execution_opcode(self):
        core = [
            sass("MOV", "R0, 0x400"),
            sass("S2R", "R2, SR_CgaCtaId"),
            sass("LEA", "R0, R2, R0, 0x18"),
            sass("LDS", "R0, [R0]"),
        ]
        audited, status, _ = analyze.audit_semantic_sequence(
            ptx("ld.shared.b32 %r0, [smem_data];", "07_lsu", "L01"), core
        )
        self.assertEqual(status, "VERIFIED")
        self.assertEqual([item["opcode"] for item in audited], ["LDS"])

    def test_atomic_audit_excludes_descriptor_preparation(self):
        core = [
            sass("R2UR", "UR4, R4"),
            sass("R2UR", "UR5, R5"),
            sass("ATOMG.E.ADD.STRONG.GPU", "PT, R0, desc[UR4][R2.64], R0"),
        ]
        audited, status, _ = analyze.audit_semantic_sequence(
            ptx("atom.global.add.u32 %old, [%addr], %r0;", "10_atomic", "A01"),
            core,
        )
        self.assertEqual(status, "VERIFIED")
        self.assertEqual(len(audited), 1)

    def test_unaudited_family_stays_pending(self):
        audited, status, _ = analyze.audit_semantic_sequence(
            ptx("mbarrier.arrive.shared.b64 _, [%bar];", "03_mbarrier", "B02"),
            [sass("ATOMS.ARRIVE", "R0, [R2]")],
        )
        self.assertEqual(status, "PENDING")
        self.assertEqual(audited, [])

    def test_integer_width_split_is_retained(self):
        core = [
            sass("IADD3", "R2, P0, PT, R0, R4, RZ"),
            sass("IADD3.X", "R3, PT, PT, R1, R5, RZ, P0, !PT"),
        ]
        audited, status, _ = analyze.audit_semantic_sequence(
            ptx("add.s64 %rd2, %rd0, %rd1;", "05_cuda_core_int", "I02"), core
        )
        self.assertEqual(status, "VERIFIED")
        self.assertEqual(audited, core)

    def test_mbarrier_audit_removes_shared_address_construction(self):
        core = [
            sass("MOV", "R0, 0x400"),
            sass("S2R", "R2, SR_CgaCtaId"),
            sass("LEA", "R0, R2, R0, 0x18"),
            sass("SYNCS.ARRIVE.TRANS64.A1T0", "R2, [R0+URZ], RZ"),
        ]
        audited, status, _ = analyze.audit_semantic_sequence(
            ptx("mbarrier.arrive.shared::cta.b64 _, [smem_mbar];", "03_mbarrier", "B02"),
            core,
        )
        self.assertEqual(status, "VERIFIED")
        self.assertEqual([item["opcode"] for item in audited], ["SYNCS.ARRIVE.TRANS64.A1T0"])

    def test_redux_audit_keeps_collective_and_uniform_result_route(self):
        core = [
            sass("MOV", "R2, R0"),
            sass("MOV", "R0, 0xffffffff"),
            sass("WARPSYNC.COLLECTIVE", "R0, `(.L_x_0)"),
            sass("REDUX.SUM.S32", "UR79, R2"),
            sass("MOV", "R0, UR79"),
            sass("ENDCOLLECTIVE"),
        ]
        audited, status, _ = analyze.audit_semantic_sequence(
            ptx("redux.sync.add.s32 %r1, %r0, 0xffffffff;", "13_warp_comm", "W05"),
            core,
        )
        self.assertEqual(status, "VERIFIED")
        self.assertEqual(len(audited), 4)

    def test_tma_audit_excludes_shared_address_and_coordinate_setup(self):
        core = [
            sass("MOV", "R0, 0x400"),
            sass("S2R", "R2, SR_CgaCtaId"),
            sass("LEA", "R0, R2, R0, 0x18"),
            sass("MOV", "R2, R3"),
            sass("R2UR", "UR4, R2"),
            sass("R2UR", "UR8, R0"),
            sass("UTMALDG.2D", "[UR8], [UR4]"),
        ]
        audited, status, _ = analyze.audit_semantic_sequence(
            ptx("cp.async.bulk.tensor.2d.shared::cta.global.mbarrier::complete_tx::bytes ...;", "02_tma", "M01"),
            core,
        )
        self.assertEqual(status, "VERIFIED")
        self.assertEqual(
            [item["opcode"] for item in audited],
            ["R2UR", "R2UR", "UTMALDG.2D"],
        )

    def test_tcgen_mma_audit_keeps_uniform_collective_protocol(self):
        core = [
            sass("SEL", "R8, RZ, 0x1, !P0"),
            sass("ISETP.NE.AND", "P0, PT, R8, RZ, PT"),
            sass("R2UR", "UR4, R4"),
            sass("VOTEU.ANY", "UP0, P0"),
            sass("UTCHMMA", "gdesc[UR4], tmem[UR10]"),
        ]
        audited, status, _ = analyze.audit_semantic_sequence(
            ptx("tcgen05.mma.cta_group::1.kind::tf32 ...;", "01_tcgen05", "T01"),
            core,
        )
        self.assertEqual(status, "VERIFIED")
        self.assertEqual(
            [item["opcode"] for item in audited],
            ["R2UR", "VOTEU.ANY", "UTCHMMA"],
        )


if __name__ == "__main__":
    unittest.main()

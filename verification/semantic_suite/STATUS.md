# Composed semantic suite status

This file records the evidence class of the composed tests.  It deliberately
does **not** derive its status from whether a PTX file exists or whether a
local `ptxas` command returned zero.

| Family | Current evidence class | B200 runtime record | What a passing run proves |
|---|---|---|---|
| `mbarrier` | `RUNTIME_VALIDATED_B200` | `2026-07-24`, O0/O3 runtime pass | Init, ordinary/transaction/drop arrival accounting, wait/acquire, consumer visibility, and inval occur in one CTA kernel. |
| `tma` | `RUNTIME_VALIDATED_B200` | `2026-07-24`, O0/O3 runtime pass | Full-tile TMA load completion through mbarrier, classic `cp.async` group completion, and TMA bulk-group completion are observable through host checks. |
| `tcgen05` | `STRUCTURAL_COMPILE_ONLY` | `2026-07-24`, O0/O3 B200 structural compile pass | The complete alloc → MMA → commit → wait → fence → load/wait → dealloc → relinquish → inval control-flow structure compiles and contains expected SASS classes; it does **not** prove MMA numerical correctness. |

`RUNTIME_CAPABLE` means that the family has a host runner and a specified
output oracle.  It is not a B200 PASS.  A row becomes `RUNTIME_VALIDATED_B200`
only after an immutable run record gives all of the following:

1. B200 GPU name/UUID, driver version, CUDA toolkit and `ptxas` version;
2. exact `run_all.sh` or family command, architecture and device ordinal;
3. O0 and O3 cubin plus `nvdisasm -g` and `-gp` evidence;
4. host output checks that passed; and
5. the dispatcher `run-summary.tsv` and matching family logs.

## Recording a B200 run

Append a dated entry after a successful run; do not replace prior records.

| UTC date | Family | GPU / UUID | CUDA / driver | Command | Artifact directory | Result |
|---|---|---|---|---|---|---|
| 2026-07-24 06:18Z | `mbarrier` | NVIDIA B200 / `GPU-90518175-3702-4bfe-31c9-578f1592d5d3` | CUDA 12.8, ptxas 12.8.93, driver 580.159.03 | `env CUDA_HOME=/usr/local/cuda-12.8 timeout 600s bash /workspace/PTX_To_SASS/verification/semantic_suite/run_all.sh --out-dir /workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260724T061600Z_final --keep-going` | `/workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260724T061600Z_final/mbarrier` | `RUNTIME_PASS`: O0/O3; 4 host-oracle kernels passed. |
| 2026-07-24 06:18Z | `tma` | NVIDIA B200 / `GPU-90518175-3702-4bfe-31c9-578f1592d5d3` | CUDA 12.8, ptxas 12.8.93, driver 580.159.03 | `env CUDA_HOME=/usr/local/cuda-12.8 timeout 600s bash /workspace/PTX_To_SASS/verification/semantic_suite/run_all.sh --out-dir /workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260724T061600Z_final --keep-going` | `/workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260724T061600Z_final/tma` | `RUNTIME_PASS`: O0/O3; TMA load, classic cp.async, and bulk-store oracles passed. |
| 2026-07-24 06:18Z | `tcgen05` | NVIDIA B200 / `GPU-90518175-3702-4bfe-31c9-578f1592d5d3` | CUDA 12.8, ptxas 12.8.93, driver 580.159.03 | `env CUDA_HOME=/usr/local/cuda-12.8 timeout 600s bash /workspace/PTX_To_SASS/verification/semantic_suite/run_all.sh --out-dir /workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260724T061600Z_final --keep-going` | `/workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260724T061600Z_final/tcgen05` | `STRUCTURAL_COMPILE_PASS` at O0/O3; no kernel launch or numerical claim. |

The dispatcher writes a per-invocation `run-summary.tsv` and `environment.txt`
under `semantic_suite/artifacts/`.  These generated files are ignored by Git;
when a B200 result is promoted to repository evidence, summarize it here or in
the family README with the exact artifact path and command.

# Composed semantic suite status

This file records the evidence class of the composed tests.  It deliberately
does **not** derive its status from whether a PTX file exists or whether a
local `ptxas` command returned zero.

| Family | Current evidence class | B200 runtime record | What a passing run proves |
|---|---|---|---|
| `mbarrier` | `RUNTIME_VALIDATED_B200` | `2026-07-27`, O0/O3 runtime pass | CTA arrive/transaction/drop accounting, four-phase reuse, and remote cluster arrive → acquire → DSMEM read are observable. |
| `tma` | `RUNTIME_VALIDATED_B200` | `2026-07-27`, O0/O3 runtime pass | 2D/3D TMA, reduce-add, pitched layout, swizzle round-trip, 2-CTA multicast, classic/bulk async completion are host-checked; prefetch is execution-only. |
| `tcgen05` | `RUNTIME_VALIDATED_B200` | `2026-07-27`, O0/O3 runtime pass | Retained raw lifecycle structural evidence plus CuTe-generated real-descriptor F16/BF16/TF32 CG1 and F16 CG2 numerical GEMM host oracles. |

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
| 2026-07-27 09:34Z | `mbarrier` | NVIDIA B200 / `GPU-57763773-1c85-4260-7159-cacae400a77d` | CUDA 12.8, ptxas 12.8.93, driver 580.105.08 | `env CUDA_HOME=/usr/local/cuda-12.8 CUTLASS_ROOT=/workspace/PTX_To_SASS/third_party/cutlass timeout 3600s bash /workspace/PTX_To_SASS/verification/semantic_suite/run_all.sh --arch sm_100a --cuda-home /usr/local/cuda-12.8 --device 0 --out-dir verification/semantic_suite/artifacts/b200_20260727T093435Z_full_semantic_final --keep-going` | `/workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260727T093435Z_full_semantic_final/mbarrier` | `RUNTIME_PASS`: O0/O3; 5 CTA oracles and 1 remote-cluster oracle passed. |
| 2026-07-27 09:34Z | `tma` | NVIDIA B200 / `GPU-57763773-1c85-4260-7159-cacae400a77d` | CUDA 12.8, ptxas 12.8.93, driver 580.105.08 | `env CUDA_HOME=/usr/local/cuda-12.8 CUTLASS_ROOT=/workspace/PTX_To_SASS/third_party/cutlass timeout 3600s bash /workspace/PTX_To_SASS/verification/semantic_suite/run_all.sh --arch sm_100a --cuda-home /usr/local/cuda-12.8 --device 0 --out-dir verification/semantic_suite/artifacts/b200_20260727T093435Z_full_semantic_final --keep-going` | `/workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260727T093435Z_full_semantic_final/tma` | `RUNTIME_PASS`: O0/O3 for 2D/3D, reduce, layout, swizzle, multicast, classic/bulk cases; prefetch `RUNTIME_EXECUTED`. |
| 2026-07-27 09:34Z | `tcgen05` | NVIDIA B200 / `GPU-57763773-1c85-4260-7159-cacae400a77d` | CUDA 12.8, ptxas 12.8.93, driver 580.105.08; CUTLASS v4.2.1 | `env CUDA_HOME=/usr/local/cuda-12.8 CUTLASS_ROOT=/workspace/PTX_To_SASS/third_party/cutlass timeout 3600s bash /workspace/PTX_To_SASS/verification/semantic_suite/run_all.sh --arch sm_100a --cuda-home /usr/local/cuda-12.8 --device 0 --out-dir verification/semantic_suite/artifacts/b200_20260727T093435Z_full_semantic_final --keep-going` | `/workspace/PTX_To_SASS/verification/semantic_suite/artifacts/b200_20260727T093435Z_full_semantic_final/tcgen05` | `RUNTIME_PASS`: raw lifecycle O0/O3 plus F16/BF16/TF32 CG1 and F16 CG2, each at O0/O3 (8 numerical oracles). |

The dispatcher writes a per-invocation `run-summary.tsv` and `environment.txt`
under `semantic_suite/artifacts/`.  These generated files are ignored by Git;
when a B200 result is promoted to repository evidence, summarize it here or in
the family README with the exact artifact path and command.

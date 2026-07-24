#!/usr/bin/env bash
# =============================================================================
# CTA mbarrier semantic suite for B200
#
# Builds a composed PTX protocol, disassembles it, and executes all three entries
# through the CUDA Driver API.  This is intentionally separate from
# verification/ptx_sources, whose files are STATIC_MAPPING evidence only.
#
# Usage:
#   CUDA_HOME=/usr/local/cuda-12.8 bash verification/semantic_suite/mbarrier/run.sh
#   bash verification/semantic_suite/mbarrier/run.sh --arch sm_100a --compile-only
#   bash verification/semantic_suite/mbarrier/run.sh --cuda-home /usr/local/cuda-12.8 \
#       --device 0 --out-dir /tmp/mbarrier-results
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCH="sm_100a"
COMPILE_ONLY=false
SKIP_DISASM=false
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
DEVICE=0
OUT_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --arch)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: --arch requires a value" >&2
                exit 2
            fi
            ARCH="$2"
            shift 2
            ;;
        --compile-only)
            COMPILE_ONLY=true
            shift
            ;;
        --skip-disasm)
            SKIP_DISASM=true
            shift
            ;;
        --cuda-home)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: --cuda-home requires a value" >&2
                exit 2
            fi
            CUDA_HOME="$2"
            shift 2
            ;;
        --device)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: --device requires a CUDA device ordinal" >&2
                exit 2
            fi
            DEVICE="$2"
            shift 2
            ;;
        --out-dir)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: --out-dir requires a path" >&2
                exit 2
            fi
            OUT_DIR="$2"
            shift 2
            ;;
        *)
            echo "ERROR: unknown option: $1" >&2
            exit 2
            ;;
    esac
done

if [[ "$ARCH" != "sm_100a" ]]; then
    echo "ERROR: this B200 semantic suite requires --arch sm_100a." >&2
    exit 2
fi

PTXAS="${PTXAS:-$CUDA_HOME/bin/ptxas}"
NVDISASM="${NVDISASM:-$CUDA_HOME/bin/nvdisasm}"
NVCC="${NVCC:-$CUDA_HOME/bin/nvcc}"
PTX_FILE="$SCRIPT_DIR/mbarrier_semantic.ptx"
if [[ -n "$OUT_DIR" ]]; then
    BUILD_DIR="$OUT_DIR/build"
    CUBIN_DIR="$OUT_DIR/cubin"
    SASS_DIR="$OUT_DIR/sass"
else
    BUILD_DIR="$SCRIPT_DIR/build"
    CUBIN_DIR="$SCRIPT_DIR/cubin"
    SASS_DIR="$SCRIPT_DIR/sass"
fi
RUNNER="$BUILD_DIR/run_mbarrier"

for tool in "$PTXAS" "$NVCC"; do
    if [[ ! -x "$tool" ]]; then
        echo "ERROR: required CUDA tool not executable: $tool" >&2
        echo "Set CUDA_HOME=/usr/local/cuda-12.8 (or override PTXAS/NVCC)." >&2
        exit 1
    fi
done

if ! $SKIP_DISASM && [[ ! -x "$NVDISASM" ]]; then
    echo "ERROR: nvdisasm not executable: $NVDISASM" >&2
    echo "Use --skip-disasm only when a disassembly artifact is not required." >&2
    exit 1
fi

mkdir -p "$BUILD_DIR" "$CUBIN_DIR" "$SASS_DIR"
# Only replace this suite's known artifacts.  In particular, --out-dir never
# clears unrelated files that happen to be in the chosen parent directory.
rm -f "$CUBIN_DIR/mbarrier_semantic_O0.cubin" \
      "$CUBIN_DIR/mbarrier_semantic_O3.cubin" \
      "$SASS_DIR/mbarrier_semantic_O0.sass" \
      "$SASS_DIR/mbarrier_semantic_O0_gp.sass" \
      "$SASS_DIR/mbarrier_semantic_O3.sass" \
      "$SASS_DIR/mbarrier_semantic_O3_gp.sass" \
      "$BUILD_DIR/runtime_results_O0.txt" \
      "$BUILD_DIR/runtime_results_O3.txt"

echo "Using: $($PTXAS --version 2>&1 | head -1)"
echo "Target architecture: $ARCH"
echo "Output directory: ${OUT_DIR:-$SCRIPT_DIR}"

for opt in O0 O3; do
    cubin="$CUBIN_DIR/mbarrier_semantic_${opt}.cubin"
    echo "[compile] $opt"
    "$PTXAS" -arch="$ARCH" "-$opt" -lineinfo -o "$cubin" "$PTX_FILE"

    if ! $SKIP_DISASM; then
        echo "[disasm] $opt"
        "$NVDISASM" -g "$cubin" >"$SASS_DIR/mbarrier_semantic_${opt}.sass"
        "$NVDISASM" -gp "$cubin" >"$SASS_DIR/mbarrier_semantic_${opt}_gp.sass"
    fi
done

"$NVCC" -std=c++17 -O2 -o "$RUNNER" "$SCRIPT_DIR/run_mbarrier.cpp" -lcuda

if $COMPILE_ONLY; then
    echo "Compilation complete."
    exit 0
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "ERROR: nvidia-smi not found; run without --compile-only only on a B200 host." >&2
    exit 1
fi

for opt in O0 O3; do
    echo "[run] $opt"
    "$RUNNER" "$CUBIN_DIR/mbarrier_semantic_${opt}.cubin" "$DEVICE" \
        | tee "$BUILD_DIR/runtime_results_${opt}.txt"
done

echo "PASS: mbarrier semantic suite completed for O0 and O3."

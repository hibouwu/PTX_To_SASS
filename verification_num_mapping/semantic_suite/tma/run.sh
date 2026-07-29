#!/usr/bin/env bash
# Build and run the composed TMA / cp.async semantic lifecycle suite.
#
# This script deliberately does not call verification/scripts/compile_all.sh:
# semantic kernels are separate from the STATIC_MAPPING corpus.

set -euo pipefail

SUITE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PTX_DIR="$SUITE_DIR/ptx"

CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"
CXX="${CXX:-g++}"
ARCH="sm_100a"
OPT_LEVEL="all"
COMPILE_ONLY=false
OUT_DIR="$SUITE_DIR/build"
DEVICE_ARGS=()

usage() {
    cat <<'EOF'
Usage: bash run.sh [--compile-only] [--opt 0|3|all] [--arch sm_100a]
                   [--out-dir DIRECTORY] [--device ORDINAL]
                   [--cuda-home DIRECTORY]

Compiles the composed semantic kernels under ptx/ at O0 and O3 by default,
saves nvdisasm -g/-gp evidence, then (unless --compile-only is supplied)
executes both optimization levels through the CUDA Driver API.

Environment:
  CUDA_HOME  CUDA toolkit root; defaults to /usr/local/cuda.  The --cuda-home
             option takes precedence for this invocation.
  CXX        Host C++ compiler; defaults to g++.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --compile-only)
            COMPILE_ONLY=true
            shift
            ;;
        --opt)
            [[ $# -ge 2 ]] || { echo "ERROR: --opt requires 0, 3, or all" >&2; exit 2; }
            case "$2" in
                0|3|all) OPT_LEVEL="$2" ;;
                *) echo "ERROR: --opt must be 0, 3, or all" >&2; exit 2 ;;
            esac
            shift 2
            ;;
        --arch)
            [[ $# -ge 2 ]] || { echo "ERROR: --arch requires sm_100a" >&2; exit 2; }
            ARCH="$2"
            shift 2
            ;;
        --out-dir)
            [[ $# -ge 2 ]] || { echo "ERROR: --out-dir requires a directory" >&2; exit 2; }
            OUT_DIR="$2"
            shift 2
            ;;
        --cuda-home)
            [[ $# -ge 2 ]] || { echo "ERROR: --cuda-home requires a directory" >&2; exit 2; }
            CUDA_HOME="$2"
            shift 2
            ;;
        --device)
            [[ $# -ge 2 ]] || { echo "ERROR: --device requires an ordinal" >&2; exit 2; }
            DEVICE_ARGS=(--device "$2")
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ "$ARCH" != "sm_100a" ]]; then
    echo "ERROR: this B200 semantic suite requires --arch sm_100a (got $ARCH)." >&2
    exit 2
fi

PTXAS="$CUDA_HOME/bin/ptxas"
NVDISASM="$CUDA_HOME/bin/nvdisasm"
CUBIN_ROOT="$OUT_DIR/cubin"
SASS_ROOT="$OUT_DIR/sass"
RUNNER="$OUT_DIR/run_tma_semantic_suite"
RUNTIME_RESULTS="$OUT_DIR/runtime_results.txt"

[[ -x "$PTXAS" ]] || {
    echo "ERROR: ptxas not found at $PTXAS; set CUDA_HOME to CUDA Toolkit >= 12.8." >&2
    exit 2
}
[[ -x "$NVDISASM" ]] || {
    echo "ERROR: nvdisasm not found at $NVDISASM; set CUDA_HOME to CUDA Toolkit >= 12.8." >&2
    exit 2
}
command -v "$CXX" >/dev/null 2>&1 || {
    echo "ERROR: host compiler '$CXX' was not found." >&2
    exit 2
}

mkdir -p "$CUBIN_ROOT" "$SASS_ROOT"

if [[ "$OPT_LEVEL" == "all" ]]; then
    OPT_LEVELS=(0 3)
else
    OPT_LEVELS=("$OPT_LEVEL")
fi

echo "Semantic suite: $SUITE_DIR"
echo "Using: $($PTXAS --version | head -1)"
echo "Target: $ARCH, optimization levels: ${OPT_LEVELS[*]}"
echo "Artifacts: $OUT_DIR"

for opt in "${OPT_LEVELS[@]}"; do
    cubin_dir="$CUBIN_ROOT/O$opt"
    sass_dir="$SASS_ROOT/O$opt"
    mkdir -p "$cubin_dir" "$sass_dir"
    for ptx in "$PTX_DIR"/*.ptx; do
        base="$(basename "$ptx" .ptx)"
        cubin="$cubin_dir/$base.cubin"
        echo "[ptxas O$opt] $base"
        "$PTXAS" -arch="$ARCH" "-O$opt" -lineinfo -o "$cubin" "$ptx"
        "$NVDISASM" -g "$cubin" > "$sass_dir/${base}.sass"
        "$NVDISASM" -gp "$cubin" > "$sass_dir/${base}_gp.sass"
    done
done

echo "[host] run_tma_semantic_suite"
"$CXX" -std=c++17 -O2 -Wall -Wextra -Werror \
    -I"$CUDA_HOME/include" \
    "$SUITE_DIR/run_tma_semantic_suite.cpp" \
    -lcuda -o "$RUNNER"

if "$COMPILE_ONLY"; then
    echo "COMPILE-ONLY PASS: selected PTX optimization level(s), disassembly evidence, and host runner built successfully."
    echo "This is static compiler validation, not B200 runtime validation."
    exit 0
fi

echo "[run] composed semantic lifecycle checks"
: > "$RUNTIME_RESULTS"
for opt in "${OPT_LEVELS[@]}"; do
    echo "[run O$opt]" | tee -a "$RUNTIME_RESULTS"
    "$RUNNER" "$CUBIN_ROOT/O$opt" "${DEVICE_ARGS[@]}" 2>&1 | tee -a "$RUNTIME_RESULTS"
done

echo "PASS: TMA / cp.async semantic suite completed for O${OPT_LEVELS[*]// / and O}."

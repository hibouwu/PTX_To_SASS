#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CUDA_HOME_VALUE="${CUDA_HOME:-/usr/local/cuda}"
CXX_VALUE="${CXX:-g++}"
DEVICE=0
OPT=all
COMPILE_ONLY=false
KERNELS=()

usage() {
    cat <<'EOF'
Usage: ./Attention/run_sm110f.sh [options]

Compile, disassemble, and run the Attention PTX kernels on sm_110f.
With no options, all kernels are processed at O0 and O3.

Options:
  --kernel NAME       Process one kernel; may be specified more than once
  --opt 0|3|all       Optimization level (default: all)
  --device ORDINAL    CUDA device ordinal (default: 0)
  --cuda-home DIR     CUDA Toolkit root (default: $CUDA_HOME or /usr/local/cuda)
  --compile-only      Compile and disassemble without launching kernels
  -h, --help          Show this help

Environment:
  CUDA_HOME           CUDA Toolkit root
  CXX                 Host C++ compiler (default: g++)
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --kernel)
            [[ $# -ge 2 ]] || { echo "ERROR: --kernel requires a name" >&2; exit 2; }
            KERNELS+=("$2")
            shift 2
            ;;
        --opt)
            [[ $# -ge 2 ]] || { echo "ERROR: --opt requires 0, 3, or all" >&2; exit 2; }
            case "$2" in
                0|3|all) OPT="$2" ;;
                *) echo "ERROR: --opt must be 0, 3, or all" >&2; exit 2 ;;
            esac
            shift 2
            ;;
        --device)
            [[ $# -ge 2 ]] || { echo "ERROR: --device requires an ordinal" >&2; exit 2; }
            [[ "$2" =~ ^[0-9]+$ ]] || { echo "ERROR: device ordinal must be non-negative" >&2; exit 2; }
            DEVICE="$2"
            shift 2
            ;;
        --cuda-home)
            [[ $# -ge 2 ]] || { echo "ERROR: --cuda-home requires a directory" >&2; exit 2; }
            CUDA_HOME_VALUE="$2"
            shift 2
            ;;
        --compile-only)
            COMPILE_ONLY=true
            shift
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

PTXAS="$CUDA_HOME_VALUE/bin/ptxas"
NVDISASM="$CUDA_HOME_VALUE/bin/nvdisasm"
CUBIN_DIR="$SCRIPT_DIR/cubins"
SASS_DIR="$SCRIPT_DIR/sass"

[[ -x "$PTXAS" ]] || {
    echo "ERROR: ptxas not found at $PTXAS" >&2
    exit 2
}
[[ -x "$NVDISASM" ]] || {
    echo "ERROR: nvdisasm not found at $NVDISASM" >&2
    exit 2
}
command -v "$CXX_VALUE" >/dev/null 2>&1 || {
    echo "ERROR: host compiler '$CXX_VALUE' not found" >&2
    exit 2
}

if [[ ${#KERNELS[@]} -eq 0 ]]; then
    for ptx in "$SCRIPT_DIR"/*.ptx; do
        KERNELS+=("$(basename "$ptx" .ptx)")
    done
fi

for kernel in "${KERNELS[@]}"; do
    [[ -f "$SCRIPT_DIR/$kernel.ptx" ]] || {
        echo "ERROR: PTX file not found: $SCRIPT_DIR/$kernel.ptx" >&2
        exit 2
    }
    case "$kernel" in
        fused_ew|layernorm|softmax_mt|tma_bulk|transpose) ;;
        *)
            echo "ERROR: run_one_kernel.cu does not support kernel '$kernel'" >&2
            exit 2
            ;;
    esac
done

if [[ "$OPT" == all ]]; then
    OPT_LEVELS=(0 3)
else
    OPT_LEVELS=("$OPT")
fi

mkdir -p "$CUBIN_DIR" "$SASS_DIR"
TMP_BUILD="$(mktemp -d "${TMPDIR:-/tmp}/attention-sm110f.XXXXXX")"
trap 'rm -rf "$TMP_BUILD"' EXIT
RUNNER="$TMP_BUILD/run_one_kernel"

echo "[host] Building CUDA Driver API runner"
"$CXX_VALUE" -x c++ -std=c++17 -O2 -Wall -Wextra \
    -I"$CUDA_HOME_VALUE/include" \
    "$SCRIPT_DIR/run_one_kernel.cu" \
    -L"$CUDA_HOME_VALUE/lib64" -lcuda \
    -o "$RUNNER"

echo "Target: sm_110f"
echo "Kernels: ${KERNELS[*]}"
echo "Optimization levels: ${OPT_LEVELS[*]}"

for opt in "${OPT_LEVELS[@]}"; do
    for kernel in "${KERNELS[@]}"; do
        ptx="$SCRIPT_DIR/$kernel.ptx"
        cubin="$CUBIN_DIR/${kernel}_O${opt}.cubin"
        sass="$SASS_DIR/${kernel}_O${opt}.sass"
        sass_ptx="$SASS_DIR/${kernel}_O${opt}_ptxline.sass"

        echo "[ptxas O$opt] $kernel"
        "$PTXAS" -arch=sm_110f "-O$opt" -lineinfo -o "$cubin" "$ptx"

        echo "[nvdisasm -g O$opt] $kernel"
        "$NVDISASM" -g "$cubin" > "$sass"

        echo "[nvdisasm -gp O$opt] $kernel"
        "$NVDISASM" -gp "$cubin" > "$sass_ptx"

        if ! "$COMPILE_ONLY"; then
            echo "[run O$opt] $kernel"
            "$RUNNER" "$cubin" "$kernel" "$DEVICE"
        fi
    done
done

if "$COMPILE_ONLY"; then
    echo "COMPILE-ONLY PASS: cubin and SASS evidence generated for sm_110f."
else
    echo "PASS: compile, disassembly, and runtime launch completed on compute capability 11.0."
fi

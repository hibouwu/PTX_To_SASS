#!/usr/bin/env bash
# Full tcgen05 semantic suite: preserve the raw-PTX lifecycle evidence, then
# compile and run CuTe-generated descriptor cases.  Do not replace this with a
# host-supplied raw descriptor test: the descriptor has to match CTA SMEM.

set -euo pipefail

SUITE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SUITE_DIR/../../.." && pwd)"

ARCH="sm_100a"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-12.8}"
CUTLASS_ROOT="${CUTLASS_ROOT:-$REPO_DIR/third_party/cutlass}"
OUT_DIR=""
DEVICE=""
COMPILE_ONLY=false

CUTLASS_TAG="v4.2.1"
CUTLASS_REVISION="f3fde58372d33e9a5650ba7b80fc48b3b49d40c8"

usage() {
    cat <<'EOF'
Usage: CUDA_HOME=/usr/local/cuda-12.8 \
  bash verification/semantic_suite/tcgen05/run.sh [options]

Options:
  --arch ARCH           Only sm_100a is accepted (default: sm_100a).
  --out-dir DIRECTORY   Put structural/runtime evidence below DIRECTORY.
  --device INDEX        Set CUDA_VISIBLE_DEVICES while running each oracle.
  --cuda-home DIRECTORY CUDA toolkit root (default: $CUDA_HOME or CUDA 12.8).
  --cutlass-root DIR    Pinned CUTLASS checkout (default: $CUTLASS_ROOT or
                        <repo>/third_party/cutlass).
  --compile-only        Compile + disassemble O0/O3 cases; do not launch them.
  -h, --help            Show this help.

The runtime cases are sourced from NVIDIA CUTLASS v4.2.1 Blackwell CuTe
tutorials.  Their CuTe layouts create the SMEM descriptors and instruction
descriptors on device; this script never accepts a raw descriptor from host.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --arch)
            [[ $# -ge 2 ]] || { echo "ERROR: --arch needs a value" >&2; exit 2; }
            ARCH="$2"
            shift 2
            ;;
        --out-dir)
            [[ $# -ge 2 ]] || { echo "ERROR: --out-dir needs a directory" >&2; exit 2; }
            OUT_DIR="$2"
            shift 2
            ;;
        --device)
            [[ $# -ge 2 ]] || { echo "ERROR: --device needs an index" >&2; exit 2; }
            DEVICE="$2"
            shift 2
            ;;
        --cuda-home)
            [[ $# -ge 2 ]] || { echo "ERROR: --cuda-home needs a directory" >&2; exit 2; }
            CUDA_HOME="$2"
            shift 2
            ;;
        --cutlass-root)
            [[ $# -ge 2 ]] || { echo "ERROR: --cutlass-root needs a directory" >&2; exit 2; }
            CUTLASS_ROOT="$2"
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

if [[ "$ARCH" != "sm_100a" ]]; then
    echo "ERROR: tcgen05 runtime suite is defined only for sm_100a." >&2
    exit 2
fi
if [[ -n "$DEVICE" && ! "$DEVICE" =~ ^[0-9]+$ ]]; then
    echo "ERROR: --device must be a non-negative CUDA-visible-device index." >&2
    exit 2
fi

NVCC="$CUDA_HOME/bin/nvcc"
NVDISASM="$CUDA_HOME/bin/nvdisasm"
for tool in "$NVCC" "$NVDISASM"; do
    [[ -x "$tool" ]] || {
        echo "ERROR: required CUDA tool is not executable: $tool" >&2
        exit 1
    }
done
command -v git >/dev/null 2>&1 || {
    echo "ERROR: git is required to verify the pinned CUTLASS checkout." >&2
    exit 1
}
command -v perl >/dev/null 2>&1 || {
    echo "ERROR: perl is required only to make isolated BF16/TF32 source variants." >&2
    exit 1
}

if [[ ! -f "$CUTLASS_ROOT/include/cute/tensor.hpp" || \
      ! -f "$CUTLASS_ROOT/examples/cute/tutorial/blackwell/01_mma_sm100.cu" || \
      ! -f "$CUTLASS_ROOT/examples/cute/tutorial/blackwell/04_mma_tma_2sm_sm100.cu" ]]; then
    cat >&2 <<EOF
ERROR: CUTLASS v4.2.1 Blackwell tutorials were not found under:
  $CUTLASS_ROOT
On the B200 collection host use, for example:
  git clone --depth 1 --branch $CUTLASS_TAG https://github.com/NVIDIA/cutlass.git $CUTLASS_ROOT
or pass --cutlass-root /path/to/a/pinned/checkout.
EOF
    exit 1
fi

if [[ ! -d "$CUTLASS_ROOT/.git" ]]; then
    echo "ERROR: CUTLASS_ROOT must be a Git checkout so its exact revision can be verified." >&2
    exit 1
fi
actual_tag="$(git -C "$CUTLASS_ROOT" describe --tags --exact-match 2>/dev/null || true)"
actual_revision="$(git -C "$CUTLASS_ROOT" rev-parse HEAD)"
if [[ "$actual_tag" != "$CUTLASS_TAG" || "$actual_revision" != "$CUTLASS_REVISION" ]]; then
    cat >&2 <<EOF
ERROR: expected CUTLASS $CUTLASS_TAG at $CUTLASS_REVISION, got:
  tag=${actual_tag:-<no exact tag>}
  revision=$actual_revision
The descriptor-generation API is intentionally pinned; do not silently use a
different CUTLASS revision as numerical evidence.
EOF
    exit 1
fi

if [[ -n "$OUT_DIR" ]]; then
    BUILD_DIR="$OUT_DIR"
else
    BUILD_DIR="$SUITE_DIR/build"
fi
STRUCTURAL_DIR="$BUILD_DIR/structural"
RUNTIME_DIR="$BUILD_DIR/runtime"
BIN_DIR="$RUNTIME_DIR/bin"
CUBIN_DIR="$RUNTIME_DIR/cubin"
SASS_DIR="$RUNTIME_DIR/sass"
LOG_DIR="$RUNTIME_DIR/logs"
GEN_DIR="$RUNTIME_DIR/generated"
SUMMARY="$RUNTIME_DIR/summary.tsv"
mkdir -p "$BIN_DIR" "$CUBIN_DIR" "$SASS_DIR" "$LOG_DIR" "$GEN_DIR"

source_f16="$CUTLASS_ROOT/examples/cute/tutorial/blackwell/01_mma_sm100.cu"
source_cg2="$CUTLASS_ROOT/examples/cute/tutorial/blackwell/04_mma_tma_2sm_sm100.cu"
source_bf16="$GEN_DIR/01_mma_sm100_bf16.cu"
source_tf32="$GEN_DIR/01_mma_sm100_tf32.cu"

make_variant_sources() {
    cp "$source_f16" "$source_bf16"
    perl -0pi -e '
      s@#include <cutlass/half\.h>@#include <cutlass/half.h>\n#include <cutlass/bfloat16.h>@;
      s/using TypeA = cutlass::half_t;/using TypeA = cutlass::bfloat16_t;/g;
      s/using TypeB = cutlass::half_t;/using TypeB = cutlass::bfloat16_t;/g;
      s/auto type_str_a = "half_t";/auto type_str_a = "bfloat16_t";/g;
      s/auto type_str_b = "half_t";/auto type_str_b = "bfloat16_t";/g;
    ' "$source_bf16"

    cp "$source_f16" "$source_tf32"
    perl -0pi -e '
      s@#include <cutlass/half\.h>@#include <cutlass/half.h>\n#include <cutlass/tfloat32.h>@;
      s/using TypeA = cutlass::half_t;/using TypeA = cutlass::tfloat32_t;/g;
      s/using TypeB = cutlass::half_t;/using TypeB = cutlass::tfloat32_t;/g;
      s/auto type_str_a = "half_t";/auto type_str_a = "tfloat32_t";/g;
      s/auto type_str_b = "half_t";/auto type_str_b = "tfloat32_t";/g;
      s/SM100_MMA_F16BF16_SS/SM100_MMA_TF32_SS/g;
    ' "$source_tf32"

    # Fail if upstream changed one of the anchored statements.  A broad text
    # substitution could otherwise turn a CUTLASS upgrade into unknown code.
    grep -Fq 'SM100_MMA_F16BF16_SS' "$source_bf16" || {
        echo "ERROR: failed to construct the BF16 CuTe variant." >&2
        exit 1
    }
    grep -Fq 'SM100_MMA_TF32_SS' "$source_tf32" || {
        echo "ERROR: failed to construct the TF32 CuTe variant." >&2
        exit 1
    }
}

run_logged() {
    local log="$1"
    shift
    if ! "$@" >"$log" 2>&1; then
        echo "ERROR: command failed; tail of $log:" >&2
        tail -80 "$log" >&2 || true
        return 1
    fi
}

contains_success_marker() {
    local log="$1"
    grep -Fq 'Execution is successful.' "$log"
}

common_nvcc=(
    -std=c++17
    -arch="$ARCH"
    --expt-relaxed-constexpr
    -lineinfo
    -I"$CUTLASS_ROOT/include"
    -I"$CUTLASS_ROOT/tools/util/include"
    -I"$CUTLASS_ROOT/examples/common"
    -I"$CUTLASS_ROOT/examples/cute/tutorial/blackwell"
)

run_case() {
    local name="$1"
    local source="$2"
    local gemm_m="$3"
    local gemm_n="$4"
    local gemm_k="$5"

    for opt in O0 O3; do
        local opt_level="-O${opt#O}"
        local binary="$BIN_DIR/${name}_${opt}"
        local cubin="$CUBIN_DIR/${name}_${opt}.cubin"
        local sass="$SASS_DIR/${name}_${opt}.sass"
        local sass_gp="$SASS_DIR/${name}_${opt}_gp.sass"
        local build_log="$LOG_DIR/${name}_${opt}_build.log"
        local cubin_log="$LOG_DIR/${name}_${opt}_cubin.log"
        local run_log="$LOG_DIR/${name}_${opt}_run.log"

        echo "[compile] $name $opt"
        run_logged "$build_log" "$NVCC" "${common_nvcc[@]}" "$opt_level" "-Xptxas=$opt_level" \
            "$source" -o "$binary"
        run_logged "$cubin_log" "$NVCC" "${common_nvcc[@]}" --cubin "$opt_level" "-Xptxas=$opt_level" \
            "$source" -o "$cubin"
        "$NVDISASM" -g "$cubin" >"$sass"
        "$NVDISASM" -gp "$cubin" >"$sass_gp"
        if ! grep -Fq 'UTCHMMA' "$sass"; then
            echo "ERROR: $name $opt has no UTCHMMA in its cubin disassembly." >&2
            exit 1
        fi

        if "$COMPILE_ONLY"; then
            printf '%s\t%s\t%s\t%s\n' "$name" "$opt" "COMPILE_ONLY" "logs/$(basename "$build_log")" >>"$SUMMARY"
            continue
        fi

        echo "[run] $name $opt"
        if [[ -n "$DEVICE" ]]; then
            if command -v timeout >/dev/null 2>&1; then
                run_logged "$run_log" env CUDA_VISIBLE_DEVICES="$DEVICE" timeout 300s "$binary" "$gemm_m" "$gemm_n" "$gemm_k"
            else
                run_logged "$run_log" env CUDA_VISIBLE_DEVICES="$DEVICE" "$binary" "$gemm_m" "$gemm_n" "$gemm_k"
            fi
        elif command -v timeout >/dev/null 2>&1; then
            run_logged "$run_log" timeout 300s "$binary" "$gemm_m" "$gemm_n" "$gemm_k"
        else
            run_logged "$run_log" "$binary" "$gemm_m" "$gemm_n" "$gemm_k"
        fi
        if ! contains_success_marker "$run_log"; then
            echo "ERROR: $name $opt did not emit CUTLASS host-oracle success." >&2
            tail -80 "$run_log" >&2 || true
            exit 1
        fi
        printf '%s\t%s\t%s\t%s\n' "$name" "$opt" "RUNTIME_PASS" "logs/$(basename "$run_log")" >>"$SUMMARY"
    done
}

echo "CUTLASS: $CUTLASS_TAG ($CUTLASS_REVISION)"
echo "CUDA: $($NVCC --version | tail -1)"
echo "Mode: $([[ "$COMPILE_ONLY" == true ]] && echo COMPILE_ONLY || echo RUNTIME_ORACLE)"
echo "[structural] raw PTX lifecycle evidence"
CUDA_HOME="$CUDA_HOME" bash "$SUITE_DIR/run_structural.sh" --arch "$ARCH" --out-dir "$STRUCTURAL_DIR"

make_variant_sources
printf 'case\toptimization\tstatus\tlog\n' >"$SUMMARY"

# 01 uses CuTe's real one-SM SMEM descriptors.  BF16/TF32 are narrow,
# audited type substitutions of the exact upstream tutorial; the descriptor
# iterator, instruction descriptor, TMEM allocator, completion barrier,
# TMEM-to-RMEM load, and host reference remain upstream CuTe code.
run_case f16_cg1  "$source_f16"  512 1024 256
run_case bf16_cg1 "$source_bf16" 256 512 128
run_case tf32_cg1 "$source_tf32" 256 512 128

# Tutorial 04 is a real 2x1SM MMA with a 256x256x16 instruction shape and
# cluster/TMA plumbing.  It is intentionally retained as upstream source.
run_case f16_cg2 "$source_cg2" 512 1024 256

if "$COMPILE_ONLY"; then
    echo "PASS: tcgen05 structural + O0/O3 runtime cases compiled/disassembled."
else
    echo "PASS: tcgen05 structural + O0/O3 CuTe descriptor host-oracle cases passed."
fi
echo "Artifacts: $BUILD_DIR"

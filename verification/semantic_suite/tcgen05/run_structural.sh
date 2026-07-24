#!/usr/bin/env bash
# Compile and disassemble the tcgen05 composed lifecycle.  This script never
# launches the generated cubin: descriptor construction is intentionally out
# of scope until a device-side wrapper is added.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCH="sm_100a"
CUDA_HOME="${CUDA_HOME:-/usr/local/cuda-12.8}"
PTXAS="${PTXAS:-$CUDA_HOME/bin/ptxas}"
NVDISASM="${NVDISASM:-$CUDA_HOME/bin/nvdisasm}"
PTX_FILE="$SCRIPT_DIR/tcgen05_mma_lifecycle_structural.ptx"
OUT_DIR=""

usage() {
    cat <<'EOF'
Usage: CUDA_HOME=/usr/local/cuda-12.8 bash run_structural.sh [--arch sm_100a]
       [--out-dir DIRECTORY]

This is a compile/disassembly-only structural check.  It never launches a
cubin and never claims a numerical tcgen05 MMA result. With --out-dir, all
generated build/cubin/sass evidence stays below that directory.
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
    echo "ERROR: tcgen05 in this suite is defined for --arch sm_100a." >&2
    exit 2
fi

if [[ -n "$OUT_DIR" ]]; then
    BUILD_DIR="$OUT_DIR"
    CUBIN_DIR="$OUT_DIR/cubin"
    SASS_DIR="$OUT_DIR/sass"
else
    BUILD_DIR="$SCRIPT_DIR/build"
    CUBIN_DIR="$BUILD_DIR/cubin"
    SASS_DIR="$BUILD_DIR/sass"
fi

for tool in "$PTXAS" "$NVDISASM"; do
    if [[ ! -x "$tool" ]]; then
        echo "ERROR: required CUDA tool is not executable: $tool" >&2
        echo "Set CUDA_HOME=/usr/local/cuda-12.8 or override PTXAS/NVDISASM." >&2
        exit 1
    fi
done

# The B200 image need not carry ripgrep. Prefer it when available, but keep
# this evidence collector runnable with the POSIX-adjacent grep supplied by
# minimal CUDA containers.
if command -v rg >/dev/null 2>&1; then
    MARKER_SEARCH="rg"
elif command -v grep >/dev/null 2>&1; then
    MARKER_SEARCH="grep"
else
    echo "ERROR: neither rg nor grep is available for structural marker checks." >&2
    exit 1
fi

mkdir -p "$CUBIN_DIR" "$SASS_DIR"
# Do not clear a whole evidence directory: a user may keep other structural
# experiments beside this one.  ptxas/nvdisasm below replace only these four
# suite-owned names atomically enough for a single invocation.
rm -f \
    "$CUBIN_DIR/tcgen05_mma_lifecycle_structural_O0.cubin" \
    "$CUBIN_DIR/tcgen05_mma_lifecycle_structural_O3.cubin" \
    "$SASS_DIR/tcgen05_mma_lifecycle_structural_O0.sass" \
    "$SASS_DIR/tcgen05_mma_lifecycle_structural_O0_gp.sass" \
    "$SASS_DIR/tcgen05_mma_lifecycle_structural_O3.sass" \
    "$SASS_DIR/tcgen05_mma_lifecycle_structural_O3_gp.sass"

require_sass_marker() {
    local marker="$1"
    local sass_file="$2"
    local found=false
    if [[ "$MARKER_SEARCH" == "rg" ]]; then
        rg -q -- "$marker" "$sass_file" && found=true
    else
        grep -Eq -- "$marker" "$sass_file" && found=true
    fi
    if ! "$found"; then
        echo "ERROR: expected SASS marker not found: $marker ($sass_file)" >&2
        exit 1
    fi
}

require_ptx_marker() {
    local marker="$1"
    local found=false
    if [[ "$MARKER_SEARCH" == "rg" ]]; then
        rg -Fq -- "$marker" "$PTX_FILE" && found=true
    else
        grep -Fq -- "$marker" "$PTX_FILE" && found=true
    fi
    if ! "$found"; then
        echo "ERROR: expected lifecycle PTX statement not found: $marker" >&2
        exit 1
    fi
}

echo "Using: $($PTXAS --version 2>&1 | head -1)"
echo "Mode: STRUCTURAL_COMPILE_ONLY (no CUDA launch)"
echo "Marker search: $MARKER_SEARCH"

# tcgen05.wait::ld has no stable standalone SASS opcode: current toolchains
# lower it to surrounding warp ordering (or an O3 NOP).  Check it directly in
# the PTX structure rather than pretending a particular SASS mnemonic proves
# the wait.  The other source-only lifecycle operations below have explicit
# SASS markers as well.
require_ptx_marker 'tcgen05.wait::ld.sync.aligned;'
require_ptx_marker 'tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;'
require_ptx_marker 'mbarrier.inval.shared::cta.b64 [smem_mbar];'

for opt in O0 O3; do
    cubin="$CUBIN_DIR/tcgen05_mma_lifecycle_structural_${opt}.cubin"
    sass="$SASS_DIR/tcgen05_mma_lifecycle_structural_${opt}.sass"
    sass_ptx="$SASS_DIR/tcgen05_mma_lifecycle_structural_${opt}_gp.sass"

    echo "[compile] $opt"
    "$PTXAS" -arch="$ARCH" "-$opt" -lineinfo -o "$cubin" "$PTX_FILE"
    echo "[disasm] $opt"
    "$NVDISASM" -g "$cubin" >"$sass"
    "$NVDISASM" -gp "$cubin" >"$sass_ptx"

    # These are structural evidence only; exact surrounding scheduling code
    # may differ between O0/O3 and CUDA toolchain versions.
    require_sass_marker 'UTCATOMSWS\.FIND_AND_SET\.ALIGN' "$sass"
    require_sass_marker 'UTCHMMA' "$sass"
    require_sass_marker 'UTCBAR' "$sass"
    require_sass_marker 'SYNCS\.PHASECHK.*TRYWAIT' "$sass"
    require_sass_marker 'LDTM' "$sass"
    require_sass_marker 'UTCATOMSWS\.AND' "$sass"
    require_sass_marker 'UVIRTCOUNT\.DEALLOC\.SMPOOL' "$sass"
    require_sass_marker 'SYNCS\.CCTL\.IV' "$sass"
done

echo "PASS: O0/O3 structural lifecycle compiled and disassembled."
echo "Artifacts: $BUILD_DIR (ignored by Git; not runtime validation evidence)."

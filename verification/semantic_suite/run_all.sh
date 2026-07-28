#!/usr/bin/env bash
# =============================================================================
# Composed semantic suite dispatcher
#
# This intentionally does not call verification/scripts/run_all.sh.  The
# STATIC_MAPPING corpus and composed runtime protocols have different source
# scopes, artifacts, and claims of evidence.
#
# Runtime families use the common ABI documented in README.md.  tcgen05 first
# collects retained raw-PTX structural evidence, then runs CuTe-generated
# real-descriptor numerical cases in its own evidence directory.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCH="sm_100a"
CUDA_HOME_VALUE="${CUDA_HOME:-/usr/local/cuda-12.8}"
DEVICE="0"
COMPILE_ONLY=false
KEEP_GOING=false
LIST_ONLY=false
OUT_DIR=""
declare -a SELECTED=()
declare -a SKIPPED=()

FAMILIES=(mbarrier tma tcgen05)

usage() {
    cat <<'EOF'
Usage: bash verification/semantic_suite/run_all.sh [options]

Options:
  --arch ARCH          Target architecture (default: sm_100a).
  --cuda-home PATH     CUDA toolkit root (default: $CUDA_HOME or
                        /usr/local/cuda-12.8).
  --device ORDINAL     CUDA device passed to runtime families (default: 0).
  --out-dir DIR        Dispatcher log directory; runtime family outputs are
                        placed below DIR/<family>.
  --compile-only       Compile/disassemble only; do not launch runtime families.
  --family NAME        Run only NAME. May be repeated.
  --skip NAME          Skip NAME. May be repeated.
  --skip-NAME          Shorthand for --skip NAME, e.g. --skip-tcgen05.
  --keep-going         Continue with later families after a failure.
  --list               List registered families and their evidence modes.
  -h, --help           Show this help.

Registered families:
  mbarrier  runtime-capable
  tma       runtime-capable (TMA and cp.async)
  tcgen05   runtime-capable; retained structural PTX plus CuTe numerical oracle
EOF
}

contains() {
    local needle="$1"
    shift
    local item
    for item in "$@"; do
        [[ "$item" == "$needle" ]] && return 0
    done
    return 1
}

is_registered_family() {
    contains "$1" "${FAMILIES[@]}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --arch)
            [[ $# -ge 2 ]] || { echo "ERROR: --arch requires a value" >&2; exit 2; }
            ARCH="$2"
            shift 2
            ;;
        --cuda-home)
            [[ $# -ge 2 ]] || { echo "ERROR: --cuda-home requires a path" >&2; exit 2; }
            CUDA_HOME_VALUE="$2"
            shift 2
            ;;
        --device)
            [[ $# -ge 2 ]] || { echo "ERROR: --device requires an ordinal" >&2; exit 2; }
            DEVICE="$2"
            shift 2
            ;;
        --out-dir)
            [[ $# -ge 2 ]] || { echo "ERROR: --out-dir requires a path" >&2; exit 2; }
            OUT_DIR="$2"
            shift 2
            ;;
        --compile-only)
            COMPILE_ONLY=true
            shift
            ;;
        --family)
            [[ $# -ge 2 ]] || { echo "ERROR: --family requires a name" >&2; exit 2; }
            SELECTED+=("$2")
            shift 2
            ;;
        --skip)
            [[ $# -ge 2 ]] || { echo "ERROR: --skip requires a name" >&2; exit 2; }
            SKIPPED+=("$2")
            shift 2
            ;;
        --skip-*)
            SKIPPED+=("${1#--skip-}")
            shift
            ;;
        --keep-going)
            KEEP_GOING=true
            shift
            ;;
        --list)
            LIST_ONLY=true
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
    echo "ERROR: the composed semantic suite is defined only for --arch sm_100a." >&2
    exit 2
fi

for family in "${SELECTED[@]}" "${SKIPPED[@]}"; do
    [[ -z "$family" ]] && continue
    if ! is_registered_family "$family"; then
        echo "ERROR: unknown family '$family'; use --list." >&2
        exit 2
    fi
done

if $LIST_ONLY; then
    printf '%-12s %-28s %s\n' "FAMILY" "EVIDENCE_MODE" "RUNNER"
    printf '%-12s %-28s %s\n' "mbarrier" "RUNTIME_CAPABLE" "mbarrier/run.sh"
    printf '%-12s %-28s %s\n' "tma" "RUNTIME_CAPABLE" "tma/run.sh"
    printf '%-12s %-28s %s\n' "tcgen05" "RUNTIME_CAPABLE" "tcgen05/run.sh"
    exit 0
fi

if [[ -z "$OUT_DIR" ]]; then
    OUT_DIR="$SCRIPT_DIR/artifacts/$(date -u +%Y%m%dT%H%M%SZ)"
fi

if [[ -e "$OUT_DIR" ]]; then
    echo "ERROR: refusing to overwrite existing --out-dir: $OUT_DIR" >&2
    echo "Choose a new path; suite runs are intended to preserve evidence." >&2
    exit 2
fi

mkdir -p "$OUT_DIR/logs"
SUMMARY="$OUT_DIR/run-summary.tsv"
ENVIRONMENT="$OUT_DIR/environment.txt"
printf 'family\tevidence_mode\tresult\tlog\n' >"$SUMMARY"

{
    echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "hostname=$(hostname)"
    echo "arch=$ARCH"
    echo "cuda_home=$CUDA_HOME_VALUE"
    echo "device=$DEVICE"
    echo "compile_only=$COMPILE_ONLY"
    echo
    echo "[ptxas]"
    "$CUDA_HOME_VALUE/bin/ptxas" --version 2>&1 || true
    echo
    echo "[nvdisasm]"
    "$CUDA_HOME_VALUE/bin/nvdisasm" --version 2>&1 || true
    echo
    echo "[nvidia-smi: name, UUID, driver]"
    nvidia-smi --query-gpu=name,uuid,driver_version --format=csv,noheader 2>&1 || true
    echo
    echo "[nvidia-smi: topology]"
    nvidia-smi -L 2>&1 || true
} >"$ENVIRONMENT"

family_will_run() {
    local family="$1"
    if [[ ${#SELECTED[@]} -gt 0 ]] && ! contains "$family" "${SELECTED[@]}"; then
        return 1
    fi
    if contains "$family" "${SKIPPED[@]}"; then
        return 1
    fi
    return 0
}

run_runtime_family() {
    local family="$1"
    local runner="$SCRIPT_DIR/$family/run.sh"
    local family_out="$OUT_DIR/$family"
    local log="$OUT_DIR/logs/$family.log"
    local -a command=(bash "$runner" --arch "$ARCH" --out-dir "$family_out" --device "$DEVICE" --cuda-home "$CUDA_HOME_VALUE")

    if $COMPILE_ONLY; then
        command+=(--compile-only)
    fi

    if [[ ! -f "$runner" ]]; then
        echo "ERROR: registered runtime runner missing: $runner" | tee "$log" >&2
        printf '%s\t%s\t%s\t%s\n' "$family" "RUNTIME_CAPABLE" "MISSING_RUNNER" "logs/$family.log" >>"$SUMMARY"
        return 1
    fi

    echo "================================================================"
    echo "[$family] ${command[*]}"
    echo "================================================================"
    if "${command[@]}" 2>&1 | tee "$log"; then
        if $COMPILE_ONLY; then
            printf '%s\t%s\t%s\t%s\n' "$family" "RUNTIME_CAPABLE" "STRUCTURAL_COMPILE_PASS" "logs/$family.log" >>"$SUMMARY"
        else
            printf '%s\t%s\t%s\t%s\n' "$family" "RUNTIME_CAPABLE" "RUNTIME_PASS" "logs/$family.log" >>"$SUMMARY"
        fi
        return 0
    fi

    printf '%s\t%s\t%s\t%s\n' "$family" "RUNTIME_CAPABLE" "FAIL" "logs/$family.log" >>"$SUMMARY"
    return 1
}

failed=false
for family in "${FAMILIES[@]}"; do
    if ! family_will_run "$family"; then
        printf '%s\t%s\t%s\t%s\n' \
            "$family" \
            "RUNTIME_CAPABLE" \
            "SKIPPED" \
            "-" >>"$SUMMARY"
        continue
    fi

    run_runtime_family "$family" || failed=true

    if $failed && ! $KEEP_GOING; then
        echo "Stopping after failure (use --keep-going to continue)." >&2
        break
    fi
done

echo
echo "================================================================"
echo "Composed semantic suite summary: $SUMMARY"
column -t -s $'\t' "$SUMMARY" 2>/dev/null || cat "$SUMMARY"
echo "Dispatcher environment: $ENVIRONMENT"
echo "================================================================"

if $failed; then
    exit 1
fi

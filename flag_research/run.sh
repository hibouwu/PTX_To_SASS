#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PTX_DIR="$SCRIPT_DIR/ptx"
ANALYZER="$SCRIPT_DIR/scripts/analyze.py"

ARCH="sm_80"
OUT_DIR="$SCRIPT_DIR/results"
KEEP=false

usage() {
    cat <<'EOF'
Usage: ./run.sh [--arch sm_80] [--out DIR] [--keep]

Compile every PTX case with ptxas -O0, -O1, -O2, and -O3, disassemble with
nvdisasm, and produce CSV/Markdown summaries. The FMA case is also compiled
with -fmad=false as a semantic-control experiment.
EOF
}

while (($#)); do
    case "$1" in
        --arch)
            [[ $# -ge 2 ]] || { echo "ERROR: --arch needs a value" >&2; exit 2; }
            ARCH="$2"; shift 2 ;;
        --out)
            [[ $# -ge 2 ]] || { echo "ERROR: --out needs a value" >&2; exit 2; }
            OUT_DIR="$2"; shift 2 ;;
        --keep)
            KEEP=true; shift ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage >&2
            exit 2 ;;
    esac
done

for tool in ptxas nvdisasm python3; do
    command -v "$tool" >/dev/null ||
        { echo "ERROR: required tool '$tool' not found in PATH" >&2; exit 1; }
done

RESULT_MARKER="$OUT_DIR/.flag_research_results"
if [[ -d "$OUT_DIR" && ! -e "$RESULT_MARKER" ]]; then
    if find "$OUT_DIR" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
        echo "ERROR: refusing to clean unmarked, non-empty output directory: $OUT_DIR" >&2
        echo "Choose a new --out directory or move its existing contents first." >&2
        exit 2
    fi
fi
mkdir -p "$OUT_DIR"
touch "$RESULT_MARKER"

if [[ "$KEEP" == false ]]; then
    rm -rf "$OUT_DIR/cubin" "$OUT_DIR/sass" "$OUT_DIR/log"
    rm -f "$OUT_DIR/build_metrics.csv" "$OUT_DIR/sass_matrix.csv" \
        "$OUT_DIR/report.md" "$OUT_DIR/toolchain.txt"
fi
mkdir -p "$OUT_DIR/cubin" "$OUT_DIR/sass" "$OUT_DIR/log"

{
    echo "date_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "arch=$ARCH"
    echo "host=$(uname -srmo)"
    echo
    ptxas --version
    echo
    nvdisasm --version
} >"$OUT_DIR/toolchain.txt"

printf 'case,profile,level,seconds,cubin_bytes,registers,compile_status\n' \
    >"$OUT_DIR/build_metrics.csv"

compile_one() {
    local src="$1"
    local profile="$2"
    local level="$3"
    local base cubin sass log timing status bytes registers
    local -a extra=()

    base="$(basename "$src" .ptx)"
    [[ "$profile" == "fmad_off" ]] && extra=(-fmad=false)
    cubin="$OUT_DIR/cubin/${base}_${profile}_O${level}.cubin"
    sass="$OUT_DIR/sass/${base}_${profile}_O${level}.sass"
    log="$OUT_DIR/log/${base}_${profile}_O${level}.log"
    timing="$OUT_DIR/log/${base}_${profile}_O${level}.time"
    status=ok

    if ! /usr/bin/time -f '%e' -o "$timing" \
        ptxas -arch="$ARCH" "-O$level" "${extra[@]}" -v \
        -o "$cubin" "$src" >"$log" 2>&1; then
        status=failed
    fi

    if [[ "$status" == ok ]]; then
        nvdisasm "$cubin" >"$sass" 2>>"$log"
        bytes="$(stat -c %s "$cubin")"
        registers="$(sed -n 's/.*Used \([0-9][0-9]*\) registers.*/\1/p' "$log" | tail -1)"
    else
        bytes=0
        registers=
    fi
    printf '%s,%s,%s,%s,%s,%s,%s\n' \
        "$base" "$profile" "$level" "$(cat "$timing")" "$bytes" \
        "$registers" "$status" >>"$OUT_DIR/build_metrics.csv"

    if [[ "$status" != ok ]]; then
        echo "ERROR: ptxas failed for $base $profile O$level; see $log" >&2
        return 1
    fi
}

mapfile -t CASES < <(find "$PTX_DIR" -maxdepth 1 -type f -name '*.ptx' | sort)
for src in "${CASES[@]}"; do
    for level in 0 1 2 3; do
        echo "[build] $(basename "$src") baseline O$level"
        compile_one "$src" baseline "$level"
    done
done

FMA_CASE="$PTX_DIR/06_fma_contract.ptx"
for level in 0 1 2 3; do
    echo "[build] $(basename "$FMA_CASE") fmad_off O$level"
    compile_one "$FMA_CASE" fmad_off "$level"
done

python3 "$ANALYZER" "$OUT_DIR"
echo
echo "Done:"
echo "  report:  $OUT_DIR/report.md"
echo "  matrix:  $OUT_DIR/sass_matrix.csv"
echo "  metrics: $OUT_DIR/build_metrics.csv"

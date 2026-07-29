#!/bin/bash
# =============================================================================
# PTX→SASS 1:1 映射验证 - 批量反汇编脚本
#
# 对 cubins/ 下的全部 .cubin 文件同时使用 nvdisasm -g 和 -gp 反汇编.
# -g 输出到 sass_dumps/，-gp PTX 行号证据输出到 sass_ptx_dumps/.
#
# 用法: bash scripts/disasm_all.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
CUBIN_DIR="$BASE_DIR/cubins"
SASS_DIR="$BASE_DIR/sass_dumps"
SASS_PTX_DIR="$BASE_DIR/sass_ptx_dumps"

# nvdisasm -g preserves the PTX .loc attribution needed to isolate line 100.
if ! command -v nvdisasm &> /dev/null; then
    echo "ERROR: nvdisasm not found in PATH. Please install CUDA Toolkit >= 12.8."
    exit 1
fi

# 创建输出目录
mkdir -p "$SASS_DIR"
mkdir -p "$SASS_PTX_DIR"

# The directory is fully generated; remove stale dumps from earlier compile runs.
rm -f "$SASS_DIR"/*.sass "$SASS_DIR"/*.err
rm -f "$SASS_PTX_DIR"/*.sass "$SASS_PTX_DIR"/*.err

# 统计
TOTAL=0
SUCCESS=0
FAIL=0
SUCCESS_PTX=0
FAIL_PTX=0

# 收集所有 .cubin 文件
mapfile -t CUBIN_FILES < <(find "$CUBIN_DIR" -name "*.cubin" -type f | sort)

echo "Found ${#CUBIN_FILES[@]} cubin files to disassemble."
echo "============================================="
echo ""

for cubin_file in "${CUBIN_FILES[@]}"; do
    TOTAL=$((TOTAL + 1))

    base_name=$(basename "$cubin_file" .cubin)
    sass_file="$SASS_DIR/${base_name}.sass"
    sass_ptx_file="$SASS_PTX_DIR/${base_name}.sass"
    sass_err="$SASS_DIR/${base_name}.err"
    sass_ptx_err="$SASS_PTX_DIR/${base_name}.err"

    # Synthetic .loc evidence used by the analyzer.
    if nvdisasm -g "$cubin_file" > "$sass_file" 2>"$sass_err"; then
        SUCCESS=$((SUCCESS + 1))
        [[ -s "$sass_err" ]] || rm -f "$sass_err"
    else
        FAIL=$((FAIL + 1))
        echo "  [-g FAIL] $cubin_file"
    fi

    # Native PTX line mapping retained independently for cross-checking.
    if nvdisasm -gp "$cubin_file" > "$sass_ptx_file" 2>"$sass_ptx_err"; then
        SUCCESS_PTX=$((SUCCESS_PTX + 1))
        [[ -s "$sass_ptx_err" ]] || rm -f "$sass_ptx_err"
    else
        FAIL_PTX=$((FAIL_PTX + 1))
        echo "  [-gp FAIL] $cubin_file"
    fi
done

echo ""
echo "============================================="
echo "Disassembly Summary:"
echo "  Total cubins:   $TOTAL"
echo "  -g success/fail:   $SUCCESS / $FAIL"
echo "  -gp success/fail:  $SUCCESS_PTX / $FAIL_PTX"
echo "  -g output dir:     $SASS_DIR"
echo "  -gp output dir:    $SASS_PTX_DIR"
echo "============================================="

if [[ $FAIL -gt 0 || $FAIL_PTX -gt 0 ]]; then
    echo ""
    echo "WARNING: Some files failed. Check .err files in both SASS directories"
    exit 1
fi

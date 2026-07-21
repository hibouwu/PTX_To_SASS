#!/bin/bash
# =============================================================================
# PTX→SASS 1:1 映射验证 - 批量反汇编脚本
#
# 对 cubins/ 下的全部 .cubin 文件使用 cuobjdump -sass 反汇编.
# 输出到 sass_dumps/ 目录.
#
# 用法: bash scripts/disasm_all.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
CUBIN_DIR="$BASE_DIR/cubins"
SASS_DIR="$BASE_DIR/sass_dumps"

# 确认 cuobjdump 可用
if ! command -v cuobjdump &> /dev/null; then
    echo "ERROR: cuobjdump not found in PATH. Please install CUDA Toolkit >= 12.8."
    exit 1
fi

# 创建输出目录
mkdir -p "$SASS_DIR"

# 统计
TOTAL=0
SUCCESS=0
FAIL=0

# 收集所有 .cubin 文件
mapfile -t CUBIN_FILES < <(find "$CUBIN_DIR" -name "*.cubin" -type f | sort)

echo "Found ${#CUBIN_FILES[@]} cubin files to disassemble."
echo "============================================="
echo ""

for cubin_file in "${CUBIN_FILES[@]}"; do
    TOTAL=$((TOTAL + 1))

    base_name=$(basename "$cubin_file" .cubin)
    sass_file="$SASS_DIR/${base_name}.sass"

    # 反汇编
    if cuobjdump -sass "$cubin_file" > "$sass_file" 2>/dev/null; then
        SUCCESS=$((SUCCESS + 1))
    else
        FAIL=$((FAIL + 1))
        echo "  FAIL: $cubin_file"
        cuobjdump -sass "$cubin_file" > "$sass_file" 2>"$SASS_DIR/${base_name}.err" || true
    fi
done

echo ""
echo "============================================="
echo "Disassembly Summary:"
echo "  Total cubins:   $TOTAL"
echo "  Success:        $SUCCESS"
echo "  Failed:         $FAIL"
echo "  Output dir:     $SASS_DIR"
echo "============================================="

if [[ $FAIL -gt 0 ]]; then
    echo ""
    echo "WARNING: Some files failed. Check .err files in $SASS_DIR"
fi

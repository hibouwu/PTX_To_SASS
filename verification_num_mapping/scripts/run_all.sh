#!/bin/bash
# =============================================================================
# PTX→SASS 1:1 映射验证 - 一键执行全流程
#
# 步骤:
#   1. 生成 PTX 测试用例 (generate_ptx.py)
#   2. 批量编译 (compile_all.sh)
#   3. 批量反汇编 (disasm_all.sh)
#   4. 自动化分析 (analyze.py)
#   5. 生成可复现性清单 (write_manifest.py)
#
# 用法: bash scripts/run_all.sh [--arch sm_100a]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

ARCH="sm_100a"
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
        *)
            echo "ERROR: unknown option: $1" >&2
            exit 2
            ;;
    esac
done

echo "================================================================"
echo "  PTX→SASS 1:1 Mapping Verification Pipeline"
echo "  Architecture: $ARCH"
echo "================================================================"
echo ""

# Step 1: Generate PTX
echo "[Step 1/5] Generating PTX test cases..."
python3 "$SCRIPT_DIR/generate_ptx.py"
echo ""

# Step 2: Compile
echo "[Step 2/5] Compiling PTX -> cubin (O0 + O3)..."
bash "$SCRIPT_DIR/compile_all.sh" --arch "$ARCH" --continue-on-error
echo ""

# Step 3: Disassemble
echo "[Step 3/5] Disassembling cubin -> SASS (-g and -gp)..."
bash "$SCRIPT_DIR/disasm_all.sh"
echo ""

# Step 4: Analyze
echo "[Step 4/5] Analyzing SASS output..."
python3 "$SCRIPT_DIR/analyze.py" --output "$BASE_DIR/results/mapping_report.csv"
echo ""

# Step 5: Manifest
echo "[Step 5/5] Writing artifact manifest..."
python3 "$SCRIPT_DIR/write_manifest.py" --arch "$ARCH"
echo ""

echo "================================================================"
echo "  Pipeline complete!"
echo "  Report: $BASE_DIR/results/mapping_report.csv"
echo "  Manifest: $BASE_DIR/results/artifact_manifest.json"
echo "================================================================"

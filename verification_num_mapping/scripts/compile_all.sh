#!/bin/bash
# =============================================================================
# PTX→SASS 1:1 映射验证 - 批量编译脚本
#
# 对 ptx_sources/ 下的全部 .ptx 文件, 分别以 -O0 和 -O3 编译为 cubin.
# 输出到 cubins/ 目录.
#
# 用法: bash scripts/compile_all.sh [--arch sm_100a] [--continue-on-error]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
PTX_DIR="$BASE_DIR/ptx_sources"
CUBIN_DIR="$BASE_DIR/cubins"

# 默认参数
ARCH="sm_100a"
CONTINUE_ON_ERROR=false
VERBOSE=false

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --arch)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: --arch requires a value" >&2
                exit 2
            fi
            ARCH="$2"
            shift 2
            ;;
        --continue-on-error)
            CONTINUE_ON_ERROR=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# 确认 ptxas 可用
if ! command -v ptxas &> /dev/null; then
    echo "ERROR: ptxas not found in PATH. Please install CUDA Toolkit >= 12.8."
    exit 1
fi

PTXAS_VERSION=$(ptxas --version 2>&1 | head -1)
echo "Using: $PTXAS_VERSION"
echo "Target architecture: $ARCH"
echo ""

# 创建输出目录
mkdir -p "$CUBIN_DIR"
# This directory is fully generated. Starting clean prevents cubins from
# removed/renamed cases from entering a later disassembly run.
rm -f "$CUBIN_DIR"/*.cubin "$CUBIN_DIR"/*.err

# 统计
TOTAL=0
SUCCESS_O0=0
SUCCESS_O3=0
FAIL_O0=0
FAIL_O3=0
SKIPPED=0

# 收集所有 .ptx 文件
mapfile -t PTX_FILES < <(find "$PTX_DIR" -name "*.ptx" -type f | sort)

# All inputs in one run must target the same architecture as ptxas.  This
# prevents an accidental sm_100 run from being reported as the B200 sm_100a
# experiment.
mapfile -t PTX_TARGETS < <(sed -n 's/^\.target[[:space:]]\+//p' "${PTX_FILES[@]}" | sort -u)
if [[ ${#PTX_TARGETS[@]} -ne 1 || "${PTX_TARGETS[0]}" != "$ARCH" ]]; then
    echo "ERROR: PTX target(s) '${PTX_TARGETS[*]:-none}' do not match --arch '$ARCH'." >&2
    exit 2
fi

echo "Found ${#PTX_FILES[@]} PTX files to compile."
echo "============================================="
echo ""

for ptx_file in "${PTX_FILES[@]}"; do
    TOTAL=$((TOTAL + 1))

    # 从路径提取 batch/filename
    rel_path="${ptx_file#$PTX_DIR/}"
    batch_dir=$(dirname "$rel_path")
    base_name=$(basename "$ptx_file" .ptx)

    # 输出文件名
    cubin_O0="$CUBIN_DIR/${batch_dir}__${base_name}_O0.cubin"
    cubin_O3="$CUBIN_DIR/${batch_dir}__${base_name}_O3.cubin"
    err_O0="$CUBIN_DIR/${batch_dir}__${base_name}_O0.err"
    err_O3="$CUBIN_DIR/${batch_dir}__${base_name}_O3.err"

    # Never let a stale cubin or error log masquerade as the current result.
    rm -f "$cubin_O0" "$cubin_O3" "$err_O0" "$err_O3"

    # Keep specification-negative cases as evidence, but do not feed invalid
    # opcode/type combinations to ptxas during the positive mapping run.
    if grep -q "EXPECTED_UNSUPPORTED_BY_PTX_ISA:" "$ptx_file"; then
        SKIPPED=$((SKIPPED + 1))
        echo "  [SKIP] $rel_path (unsupported by PTX ISA)"
        continue
    fi

    if $VERBOSE; then
        echo "[$TOTAL] Compiling: $rel_path"
    fi

    # -O0 编译
    if ptxas -arch="$ARCH" -O0 -lineinfo -o "$cubin_O0" "$ptx_file" 2>/dev/null; then
        SUCCESS_O0=$((SUCCESS_O0 + 1))
        if $VERBOSE; then
            echo "  [O0] OK: $cubin_O0"
        fi
    else
        FAIL_O0=$((FAIL_O0 + 1))
        echo "  [O0] FAIL: $rel_path"
        # 保存错误信息
        ptxas -arch="$ARCH" -O0 -lineinfo -o "$cubin_O0" "$ptx_file" 2>"$err_O0" || true
        if ! $CONTINUE_ON_ERROR; then
            echo "Aborting (use --continue-on-error to skip failures)"
            exit 1
        fi
    fi

    # -O3 编译
    if ptxas -arch="$ARCH" -O3 -lineinfo -o "$cubin_O3" "$ptx_file" 2>/dev/null; then
        SUCCESS_O3=$((SUCCESS_O3 + 1))
        if $VERBOSE; then
            echo "  [O3] OK: $cubin_O3"
        fi
    else
        FAIL_O3=$((FAIL_O3 + 1))
        echo "  [O3] FAIL: $rel_path"
        ptxas -arch="$ARCH" -O3 -lineinfo -o "$cubin_O3" "$ptx_file" 2>"$err_O3" || true
        if ! $CONTINUE_ON_ERROR; then
            echo "Aborting (use --continue-on-error to skip failures)"
            exit 1
        fi
    fi
done

echo ""
echo "============================================="
echo "Compilation Summary:"
echo "  Total PTX files:  $TOTAL"
echo "  Skipped:          $SKIPPED"
echo "  O0 success/fail:  $SUCCESS_O0 / $FAIL_O0"
echo "  O3 success/fail:  $SUCCESS_O3 / $FAIL_O3"
echo "  Output dir:       $CUBIN_DIR"
echo "============================================="

if [[ $FAIL_O0 -gt 0 || $FAIL_O3 -gt 0 ]]; then
    echo ""
    echo "WARNING: Some files failed to compile. Check .err files in $CUBIN_DIR"
    echo "Error files:"
    find "$CUBIN_DIR" -name "*.err" -size +0c | sort
    exit 1
fi

#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
jobs="${1:-4}"
work_root="${2:-/tmp/thor-tcgen05-mma-all}"

python3 "${script_dir}/suite_utils.py" "${work_root}" >/dev/null

python3 "${script_dir}/check_cases.py" \
    --mode syntax \
    --jobs "${jobs}" \
    --work-dir "${work_root}/syntax" \
    --summary-output "${script_dir}/validation/syntax_compile_summary.json"

python3 "${script_dir}/check_cases.py" \
    --mode expanded \
    --jobs "${jobs}" \
    --work-dir "${work_root}/expanded" \
    --summary-output "${script_dir}/validation/expanded_compile_summary.json"

python3 "${script_dir}/check_negative_probes.py" \
    --work-dir "${work_root}/negative-probes" \
    --summary-output "${script_dir}/validation/negative_probe_summary.json"

python3 "${script_dir}/check_protocol_layers.py" \
    --jobs "${jobs}" \
    --work-dir "${work_root}/protocol-layers" \
    --summary-output "${script_dir}/validation/protocol_compile_summary.json"

python3 "${script_dir}/generate_cases.py"
python3 "${script_dir}/generate_protocol_layers.py"

echo "PASS: syntax + expanded + CTX.protocol + effect_slice O0/O1/O2/O3"

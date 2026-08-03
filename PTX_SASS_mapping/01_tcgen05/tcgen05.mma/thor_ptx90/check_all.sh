#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
jobs="${1:-4}"
work_root="${2:-${script_dir}/results}"

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

python3 "${script_dir}/compare_context_lowering.py" \
    --source-dir "${work_root}/expanded/sources" \
    --sass-dir "${work_root}/expanded/sass" \
    --output-dir "${work_root}/context-comparison" \
    --report-output "${script_dir}/Docs/tcgen05_mma_上下文差分报告.md"

python3 "${script_dir}/analyze_mapping_rules.py" \
    --manifest "${work_root}/expanded/sources/manifest.jsonl" \
    --attribution "${work_root}/expanded/sass/sass_attribution.jsonl" \
    --differences "${work_root}/context-comparison/context_differences.jsonl" \
    --output-dir "${work_root}/rule-mining" \
    --report-output "${script_dir}/Docs/mapping_rules/reverse_mapping_rules.md"

python3 "${script_dir}/check_negative_probes.py" \
    --work-dir "${work_root}/negative-probes" \
    --summary-output "${script_dir}/validation/negative_probe_summary.json"

python3 "${script_dir}/check_protocol_layers.py" \
    --jobs "${jobs}" \
    --work-dir "${work_root}/protocol-layers" \
    --summary-output "${script_dir}/validation/protocol_compile_summary.json"

python3 "${script_dir}/generate_cases.py"
python3 "${script_dir}/generate_protocol_layers.py"

echo "PASS: syntax + expanded + predicate/idesc encoding probes + context comparison + canonical forward/inverse rules + 30 negative boundaries + CTX.protocol + effect_slice O0/O1/O2/O3"

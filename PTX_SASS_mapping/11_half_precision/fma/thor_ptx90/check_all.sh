#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
jobs="${1:-4}"
work_root="${2:-${script_dir}/results}"

python3 "${script_dir}/check_cases.py" --mode syntax --jobs "${jobs}" --work-dir "${work_root}/syntax" --summary-output "${script_dir}/validation/syntax_compile_summary.json"
python3 "${script_dir}/check_cases.py" --mode expanded --jobs "${jobs}" --work-dir "${work_root}/expanded" --summary-output "${script_dir}/validation/expanded_compile_summary.json"
python3 "${script_dir}/analyze_mapping_rules.py" --manifest "${work_root}/expanded/sources/manifest.jsonl" --attribution "${work_root}/expanded/sass/sass_attribution.jsonl" --output-dir "${work_root}/rule-mining" --summary-output "${script_dir}/validation/mapping_rule_summary.json"
python3 "${script_dir}/check_negative_probes.py" --work-dir "${work_root}/negative-probes" --summary-output "${script_dir}/validation/negative_probe_summary.json"
python3 "${script_dir}/generate_cases.py" --mode syntax --output "${script_dir}/generated"

echo "PASS: fma syntax + expanded + O0/O1/O2/O3 attribution + rule candidates + negative boundaries"

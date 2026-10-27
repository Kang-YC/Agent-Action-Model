#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
inference_python="${BASE_MODEL_PYTHON:-${repo_root}/.venv-inference/bin/python}"
export PYTHONPATH="${repo_root}${PYTHONPATH:+:${PYTHONPATH}}"
export TOKENIZERS_PARALLELISM=false
export VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1
exec "${inference_python}" -m agent_action.serve --config "${repo_root}/configs/base_model.json" "$@"

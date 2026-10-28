#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${repo_root}${PYTHONPATH:+:${PYTHONPATH}}"
exec "${EVALUATION_WEB_PYTHON:-python3}" -u -m agent_action.evaluation_web "$@"

#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
control_python="${ROBODOJO_PYTHON:-/opt/robodojo-conda/envs/RoboDojo/bin/python}"
export PYTHONPATH="${repo_root}:${repo_root}/../GPT-as-Policy${PYTHONPATH:+:${PYTHONPATH}}"
exec "${control_python}" -m agent_action.a_line "$@"

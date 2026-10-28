#!/usr/bin/env bash
# Start a fresh native backend, then run the B-line controller after readiness.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"
output="${1:?Usage: run_b_line.sh NEW_OUTPUT_DIR [b_run arguments]}"
shift
mkdir "${output}"
output="$(cd "${output}" && pwd)"
port="${B_LINE_PORT:-19133}"
task="${B_LINE_TASK:-classify_objects}"
b_python="${B_LINE_PYTHON:-/tmp/agent-action-b-venv/bin/python}"
export PYTHONPATH="${repo_root}:${repo_root}/third_party/mini-swe-agent/src:${repo_root}/../GPT-as-Policy${PYTHONPATH:+:${PYTHONPATH}}"
export MSWEA_GLOBAL_CONFIG_DIR="${output}/mini-config"
export LITELLM_LOCAL_MODEL_COST_MAP=True
export ROBODOJO_ROOT="${ROBODOJO_ROOT:-${ROBODOJO_SHARED_ROOT:-/dataset_rc_b1/kangyc1@xiaopeng.com/robodojo_shared}/RoboDojo}"
mkdir "${output}/sim"
bash scripts/start_native.sh --task "${task}" --port "${port}" --output "${output}/sim" > "${output}/sim.log" 2>&1 &
sim_pid=$!
controller_pid=""
cleanup() {
  if [[ -n "${controller_pid}" ]] && kill -0 "${controller_pid}" 2>/dev/null; then
    kill -TERM "${controller_pid}" 2>/dev/null || true
    wait "${controller_pid}" || true
  fi
  if kill -0 "${sim_pid}" 2>/dev/null; then
    kill -TERM "${sim_pid}" 2>/dev/null || true
  fi
  wait "${sim_pid}" || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Never connect a health socket: the native backend accepts only one owner.
ready=0
for ((attempt=0; attempt<300; attempt++)); do
  if rg -q '"event": "ready"' "${output}/sim.log"; then
    ready=1
    break
  fi
  if ! kill -0 "${sim_pid}" 2>/dev/null; then
    echo "Native backend exited; inspect ${output}/sim.log" >&2
    exit 1
  fi
  sleep 2
done
if [[ "${ready}" != 1 ]]; then
  echo "Native readiness timeout; inspect ${output}/sim.log" >&2
  exit 1
fi
"${b_python}" -m agent_action.b_run --output "${output}/controller" --task "${task}" --port "${port}" --sim-output "${output}/sim" "$@" > "${output}/controller.log" 2>&1 &
controller_pid=$!
while kill -0 "${controller_pid}" 2>/dev/null; do
  if ! kill -0 "${sim_pid}" 2>/dev/null; then
    echo '{"status":"infrastructure_error","reason":"native_backend_exited"}' > "${output}/launcher_error.json"
    echo "Native backend exited during control; stopping owned controller" >&2
    kill -TERM "${controller_pid}" 2>/dev/null || true
    wait "${controller_pid}" || true
    exit 1
  fi
  sleep 2
done
wait "${controller_pid}"

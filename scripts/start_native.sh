#!/usr/bin/env bash
# Development backend only: reuse the reference robot RPC, without its agent.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
sim_root="${ROBODOJO_ROOT:-${repo_root}/../RoboDojo}"
reference_root="${GPT_AS_POLICY_ROOT:-${repo_root}/../GPT-as-Policy}"
sim_python="${ROBODOJO_PYTHON:-/opt/robodojo-conda/envs/RoboDojo/bin/python}"
shared_root="${ROBODOJO_SHARED_ROOT:-/dataset_rc_b1/kangyc1@xiaopeng.com/robodojo_shared}"
if [[ ! -f "${sim_root}/Assets/Robots/x5/robot_config.yml" ]]; then
    echo "Missing X5 assets under ${sim_root}. Set ROBODOJO_ROOT to a complete checkout (e.g. ${shared_root}/RoboDojo)." >&2
    exit 1
fi
export PYTHONPATH="${reference_root}:${sim_root}:${sim_root}/XPolicyLab:${sim_root}/third_party/IsaacLab/source/isaaclab:${PYTHONPATH:-}"
export PYTHONDONTWRITEBYTECODE=1 OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y PRIVACY_CONSENT=Y
kit_args="${ROBODOJO_KIT_ARGS:-}"
kit_args="${kit_args} --/app/updateOrder/checkForHydraRenderComplete=1000 --/app/renderer/waitIdle=true --/app/hydraEngine/waitIdle=true"
extensions="${shared_root}/runtime/current/robodojo-runtime/isaac-exts"
if [[ -d "${extensions}" ]]; then
    kit_args="${kit_args} --ext-folder=${extensions}"
fi
exec "${sim_python}" -u -m hybrid_rollout.robodojo.robodojo_server.server \
    --headless --kit_args "${kit_args}" "$@"

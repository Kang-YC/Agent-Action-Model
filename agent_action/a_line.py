"""Reproducible A-line stack-bowls development entrypoint."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=root / "configs/a_stack_bowls_development.json")
    parser.add_argument("--robodojo", type=Path, default=Path(os.environ.get("ROBODOJO_SHARED_ROOT", "/dataset_rc_b1/kangyc1@xiaopeng.com/robodojo_shared")) / "RoboDojo")
    parser.add_argument("--codex", type=Path, default=Path("/root/.codex/packages/app-server-daemon/releases/0.164.0-x86_64-unknown-linux-musl/bin/codex"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.config.read_text())
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("Use a fresh run directory; previous attempts are never overwritten")
    command = [sys.executable, "-m", "agent_action.direct", "--config", str(root / plan["model_config"]),
               "--robodojo", str(args.robodojo.resolve()), "--codex", str(args.codex.resolve()),
               "--output", str(output), "--task", plan["task"], "--seed", str(plan["layout_id"]),
               "--max-decisions", str(plan["max_decisions"]), "--max-control-steps", str(plan["max_control_steps"]),
               "--max-total-tokens", str(plan["max_total_tokens"]), "--wall-seconds", str(plan["wall_seconds"])]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.with_name(output.name + ".plan.json").open("x") as stream:
        json.dump(dict(plan=plan, config_sha256=hashlib.sha256(args.config.read_bytes()).hexdigest(), argv=command), stream, indent=2)
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()

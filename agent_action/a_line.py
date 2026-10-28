"""Reproducible A-line stack-bowls development entrypoint."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def validate_native_budget(plan: dict) -> None:
    if plan["native_control_horizon"] <= 0 or plan["max_control_steps"] != plan["native_control_horizon"]:
        raise ValueError("Control-step budget must equal the native task horizon")
    if any(plan[key] != 0 for key in ("max_decisions", "max_total_tokens", "wall_seconds")):
        raise ValueError("The reference protocol disables extra decision, token and wall-clock caps")


def published_case_plan(panel: dict, case_id: str) -> dict:
    payload = {key: value for key, value in panel.items() if key != "panel_sha256"}
    if hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest() != panel["panel_sha256"]:
        raise ValueError("Published panel hash mismatch")
    selected = [case for case in panel["cases"] if case["case_id"] == case_id]
    if len(selected) != 1:
        raise ValueError(f"Expected one published case: {case_id}")
    case = selected[0]
    return dict(route="A: local base + Codex Direct", task=case["runtime_task"], case_id=case_id,
                panel_sha256=panel["panel_sha256"], eval_seed=case["seeds"]["eval_seed"],
                layout_id=case["seeds"]["layout_id"], native_control_horizon=case["native_horizon"],
                max_control_steps=case["native_horizon"], max_decisions=0, max_total_tokens=0, wall_seconds=0,
                budget_protocol="native_control_steps_only", model_config="configs/base_model.json",
                layout=case["layout"])


def native_case_selection(plan: dict, native_panel: dict) -> dict:
    from hybrid_rollout.robodojo.evaluation import case_identity, validate_panel

    validate_panel(native_panel)
    rows = [case for case in native_panel['cases'] if case['case_id'] == plan['case_id']]
    if len(rows) != 1:
        raise ValueError('Published case is absent from the native identity panel')
    case = rows[0]
    if (case['runtime_task'], case['eval_seed'], case['layout_id'], case['layout']) != (
            plan['task'], plan['eval_seed'], plan['layout_id'], plan['layout']):
        raise ValueError('Native case identity differs from the published case')
    return dict(case=case, identity=case_identity(native_panel, case))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=root / "configs/a_stack_bowls_development.json")
    parser.add_argument("--panel", type=Path, default=root / "configs/a_published_ten_task_panel.json")
    parser.add_argument("--case-id", help="Use this frozen published case instead of the stack-bowls plan")
    parser.add_argument("--native-panel", type=Path, default=root / 'configs/a_native_panel60_v1.json')
    parser.add_argument("--robodojo", type=Path, default=Path(os.environ.get("ROBODOJO_SHARED_ROOT", "/dataset_rc_b1/kangyc1@xiaopeng.com/robodojo_shared")) / "RoboDojo")
    parser.add_argument("--codex", type=Path, default=Path("/root/.codex/packages/app-server-daemon/releases/0.164.0-x86_64-unknown-linux-musl/bin/codex"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.panel if args.case_id else args.config
    definition = json.loads(source.read_text())
    plan = published_case_plan(definition, args.case_id) if args.case_id else definition
    validate_native_budget(plan)
    if args.case_id:
        actual = hashlib.sha256((args.robodojo / plan["layout"]["path"]).read_bytes()).hexdigest()
        if actual != plan["layout"]["sha256"]:
            raise ValueError("Current layout differs from the frozen published case")
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("Use a fresh run directory; previous attempts are never overwritten")
    command = [sys.executable, "-m", "agent_action.direct", "--config", str(root / plan["model_config"]),
               "--robodojo", str(args.robodojo.resolve()), "--codex", str(args.codex.resolve()),
               "--output", str(output), "--task", plan["task"], "--seed", str(plan["layout_id"]),
               "--eval-seed", str(plan["eval_seed"]),
               "--max-decisions", str(plan["max_decisions"]), "--max-control-steps", str(plan["max_control_steps"]),
               "--max-total-tokens", str(plan["max_total_tokens"]), "--wall-seconds", str(plan["wall_seconds"])]
    output.parent.mkdir(parents=True, exist_ok=True)
    selection = None
    if args.case_id:
        native_panel = json.loads(args.native_panel.read_text())
        selection = native_case_selection(plan, native_panel)
        case_file = output.with_name(output.name + '.case.json')
        with case_file.open('x') as stream:
            json.dump(selection, stream, indent=2)
        command.extend(['--eval-manifest', str(args.native_panel.resolve()), '--case-file', str(case_file)])
    with output.with_name(output.name + ".plan.json").open("x") as stream:
        json.dump(dict(plan=plan, config_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                       evaluation_identity=selection['identity'] if selection else None, argv=command), stream, indent=2)
    os.execv(sys.executable, command)


if __name__ == "__main__":
    main()

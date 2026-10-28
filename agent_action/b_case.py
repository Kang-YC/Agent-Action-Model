"""Bind a B-line run to a published case and its native evaluator identity."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from agent_action.a_line import native_case_selection, published_case_plan, validate_native_budget

ROOT = Path(__file__).resolve().parents[1]


def prepare_case(panel_path: Path, native_panel_path: Path, case_id: str,
                 robodojo: Path, output: Path, *, history_turns: int = 8, port: int = 19135) -> dict:
    from hybrid_rollout.robodojo.evaluation import verify_assets

    if history_turns != 8:
        raise ValueError("The authorized follow-up keeps the validated eight-turn history")
    output = output.resolve()
    plan_file = Path(str(output) + ".plan.json")
    if output.exists() or any(Path(str(output) + s).exists() for s in (".plan.json", ".case.json", ".native-panel.json")):
        raise FileExistsError("Fresh attempt paths required; never overwrite or automatically retry")
    panel = json.loads(panel_path.read_text())
    native_panel = json.loads(native_panel_path.read_text())
    base = published_case_plan(panel, case_id)
    validate_native_budget(base)
    selection = native_case_selection(base, native_panel)
    verify_assets(native_panel, robodojo, [selection["case"]])
    exclusions = json.loads((ROOT / "configs/b_development_exclusions.json").read_text())["entries"]
    if any((row["runtime_task"], row["eval_seed"], row["layout_id"]) ==
           (base["task"], base["eval_seed"], base["layout_id"]) for row in exclusions):
        raise ValueError("Case was already used for B development")
    output.parent.mkdir(parents=True, exist_ok=True)
    native_copy = Path(str(output) + ".native-panel.json")
    case_file = Path(str(output) + ".case.json")
    for path, data in ((native_copy, native_panel), (case_file, selection)):
        with path.open("x") as stream:
            json.dump(data, stream, indent=2)
    plan = dict(route="B: local base + mini-swe-agent persistent Python", case_id=case_id,
                task=base["task"], eval_seed=base["eval_seed"], layout_id=base["layout_id"],
                native_control_horizon=base["native_control_horizon"], max_control_steps=base["max_control_steps"],
                max_turns=0, max_total_tokens=0, wall_seconds=0, history_turns=history_turns,
                budget_protocol="native_control_steps_only", layout=base["layout"],
                source_panel_sha256=base["panel_sha256"], evaluation_identity=selection["identity"])
    command = ["bash", str(ROOT / "scripts/run_b_line.sh"), str(output),
               "--config", str(ROOT / "configs/base_model.json"),
               "--robodojo", str(robodojo.resolve()), "--reference", str(ROOT.parent / "GPT-as-Policy"),
               "--seed", str(plan["layout_id"]), "--max-control-steps", str(plan["max_control_steps"]),
               "--max-turns", "0", "--max-total-tokens", "0", "--wall-seconds", "0", "--history-turns", "8"]
    environment = dict(B_LINE_TASK=plan["task"], B_LINE_PORT=str(port),
                       B_LINE_EVAL_SEED=str(plan["eval_seed"]), ROBODOJO_ROOT=str(robodojo.resolve()),
                       B_LINE_EVAL_MANIFEST=str(native_copy), B_LINE_CASE_FILE=str(case_file),
                       ROLLOUT_EVAL_MANIFEST_SHA256=native_panel["panel_sha256"])
    record = dict(plan=plan, argv=command, environment=environment,
                  source_panel_path=str(panel_path.resolve()),
                  source_panel_file_sha256=hashlib.sha256(panel_path.read_bytes()).hexdigest())
    with plan_file.open("x") as stream:
        json.dump(record, stream, indent=2)
    return record


def verify_prepared(record: dict) -> None:
    from hybrid_rollout.robodojo.evaluation import case_identity, read_panel, verify_assets

    env, plan = record["environment"], record["plan"]
    source = Path(record["source_panel_path"])
    if hashlib.sha256(source.read_bytes()).hexdigest() != record["source_panel_file_sha256"]:
        raise ValueError("Published budget/case source changed")
    expected = published_case_plan(json.loads(source.read_text()), plan["case_id"])
    if plan["native_control_horizon"] != expected["native_control_horizon"]:
        raise ValueError("Control horizon differs from published native limit")
    panel = read_panel(env["B_LINE_EVAL_MANIFEST"], env["ROLLOUT_EVAL_MANIFEST_SHA256"])
    selection = json.loads(Path(env["B_LINE_CASE_FILE"]).read_text())
    case = selection["case"]
    if case not in panel["cases"] or selection["identity"] != case_identity(panel, case):
        raise ValueError("Prepared native identity changed")
    if selection["identity"] != plan["evaluation_identity"]:
        raise ValueError("Plan and native identity differ")
    if (case["runtime_task"], case["eval_seed"], case["layout_id"], case["layout"]) != (
            plan["task"], plan["eval_seed"], plan["layout_id"], plan["layout"]):
        raise ValueError("Prepared task/layout changed")
    if not plan["max_control_steps"] == plan["native_control_horizon"] > 0 or any(
            plan[key] != 0 for key in ("max_turns", "max_total_tokens", "wall_seconds")):
        raise ValueError("Prepared native-only budgets changed")
    if env["B_LINE_TASK"] != case["runtime_task"] or int(env["B_LINE_EVAL_SEED"]) != case["eval_seed"]:
        raise ValueError("Prepared simulator CLI identity changed")
    for flag, value in (("--seed", plan["layout_id"]), ("--max-control-steps", plan["max_control_steps"]),
                        ("--max-turns", 0), ("--max-total-tokens", 0), ("--wall-seconds", 0), ("--history-turns", 8)):
        if record["argv"].count(flag) != 1 or record["argv"][record["argv"].index(flag) + 1] != str(value):
            raise ValueError(f"Prepared command differs from plan: {flag}")
    verify_assets(panel, env["ROBODOJO_ROOT"], [case])
    if Path(record["argv"][2]).exists():
        raise FileExistsError("Attempt output already exists; no retry")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--panel", type=Path, default=ROOT / "configs/a_published_ten_task_panel.json")
    p.add_argument("--native-panel", type=Path, default=ROOT / "configs/a_native_panel60_v1.json")
    p.add_argument("--case-id", required=True)
    p.add_argument("--robodojo", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--prepare-only", action="store_true")
    args = p.parse_args()
    sys.path.insert(0, str(ROOT.parent / "GPT-as-Policy"))
    record = prepare_case(args.panel, args.native_panel, args.case_id, args.robodojo, args.output)
    if not args.prepare_only:
        verify_prepared(record)
        os.chdir(ROOT)
        os.execvpe(record["argv"][0], record["argv"], dict(os.environ, **record["environment"]))
    print(json.dumps(record["plan"], indent=2))


if __name__ == "__main__":
    main()

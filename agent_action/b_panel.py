"""Prepare an offline B-line candidate panel; never launch or freeze evaluation."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from agent_action.a_line import published_case_plan, validate_native_budget


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def prepare(panel: dict, exclusions: dict, robodojo: Path, development_run: Path) -> dict:
    root = robodojo.resolve()
    manifest_path = development_run / "controller/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    arguments = manifest["arguments"]
    turns = arguments["history_turns"]
    if turns != 8:
        raise ValueError("Candidate protocol must reference the current window-8 development run")
    entries = exclusions["entries"]
    keys = [(e["runtime_task"], e["eval_seed"], e["layout_id"]) for e in entries]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate development exclusion")
    cases = []
    verified_assets = set()
    seen = set()
    for case in panel["cases"]:
        if case["case_id"] in seen:
            raise ValueError("Duplicate case identity")
        seen.add(case["case_id"])
        plan = published_case_plan(panel, case["case_id"])
        validate_native_budget(plan)
        for asset in [case["layout"], *case.get("native_support_trajectories", [])]:
            relative = Path(asset["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Asset escapes RoboDojo root")
            # The shared checkout deliberately symlinks Assets to shared storage.
            path = root / relative
            if hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
                raise ValueError(f"Frozen asset mismatch: {asset['path']}")
            verified_assets.add(str(path))
        key = (case["runtime_task"], case["seeds"]["eval_seed"], case["seeds"]["layout_id"])
        exclusion = entries[keys.index(key)] if key in keys else None
        cases.append(dict(
            case_id=case["case_id"], task=case["task"], runtime_task=case["runtime_task"],
            variant=case["variant"], eval_seed=key[1], layout_id=key[2],
            native_control_horizon=case["native_horizon"], layout=case["layout"],
            native_support_trajectories=case.get("native_support_trajectories", []),
            status="excluded_development" if exclusion else "candidate_not_launchable",
            exclusion=exclusion,
            proposed_controller_arguments=dict(task=case["runtime_task"], seed=key[2],
                max_control_steps=case["native_horizon"], max_turns=0,
                max_total_tokens=0, wall_seconds=0, history_turns=turns),
            required_native_identity=dict(case_id=case["case_id"], runtime_task=key[0],
                eval_seed=key[1], layout_id=key[2], layout_sha256=case["layout"]["sha256"]),
            executable_command=None))
    summary_path = development_run / "controller/summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
    eligible = [c for c in cases if c["exclusion"] is None]
    report = dict(
        schema="agent_action.b_candidate_panel.v1", status="draft_not_frozen",
        launches_processes=False, launchable_cases=0,
        source_panel_sha256=panel["panel_sha256"], exclusions_sha256=digest(exclusions),
        development_reference=dict(run=str(development_run.resolve()),
            manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            model_config_sha256=digest(manifest["model"]), history_turns=turns,
            summary_present=summary is not None, summary_status=(summary or {}).get("status")),
        activation_gates=[
            "Review stack-bowls terminal outcome, video, action rejection rate and costs",
            "Freeze B prompts, static information, history policy and source version separately from A",
            "Implement and test native eval-manifest/case-file identity binding in B launcher",
            "Freeze native evaluator/adapter source and runtime versions, beyond the controller source snapshot",
            "Revalidate layout and native-support hashes immediately before each launch",
            "Assign fresh attempt directories; preserve failures and forbid best-of selection",
            "Review exclusions and paired A/B case denominator before formal evaluation"],
        source_cases=len(cases), candidate_cases=len(eligible),
        excluded_cases=len(cases)-len(eligible), verified_unique_assets=len(verified_assets),
        candidates_by_task=dict(Counter(c["task"] for c in eligible)),
        caveat="Excluding known B development layouts does not establish universal held-out status or preserve the published 50-case denominator. No historical labels enter candidate plans.",
        cases=cases)
    # This identifies the proposal, not a frozen runnable panel or native manifest.
    report["proposal_sha256"] = digest(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, default=Path("configs/a_published_ten_task_panel.json"))
    parser.add_argument("--exclusions", type=Path, default=Path("configs/b_development_exclusions.json"))
    parser.add_argument("--robodojo", type=Path, required=True)
    parser.add_argument("--development-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New JSON proposal path")
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.development_run.resolve()):
        parser.error("Output must be outside the development run")
    if args.output.exists():
        parser.error("Use a new output path; proposals are never overwritten")
    report = prepare(json.loads(args.panel.read_text()), json.loads(args.exclusions.read_text()),
                     args.robodojo, args.development_run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    print(json.dumps({k: report[k] for k in ("status", "source_cases", "candidate_cases", "excluded_cases", "launchable_cases", "verified_unique_assets")}))


if __name__ == "__main__":
    main()

"""Freeze the exact published ten-task Direct cases for later paired evaluation."""

import argparse
import hashlib
import json
from pathlib import Path

from hybrid_rollout.robodojo.evaluation import TASKS, layout_files


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(reference: Path, robodojo: Path) -> dict:
    public = reference / "public_results/evaluation_cases.json"
    published = json.loads(public.read_text())["cases"]
    direct = [r for r in published if r["method"] == "gpt"]
    if len(direct) != 50 or {r["task"] for r in direct} != set(TASKS):
        raise ValueError("Published Direct scope differs from the expected ten tasks / fifty cases")
    historical = json.loads((reference / "hybrid_rollout/robodojo/eval_panels/robodojo_panel60_v1.json").read_text())
    historical_cases = {c["case_id"]: c for c in historical["cases"]}
    native_sources = []
    for record in historical["native_source_files"]:
        path = robodojo / record["path"]
        current = digest(path) if path.is_file() else None
        native_sources.append(dict(path=record["path"], historical_sha256=record["sha256"],
                                   current_sha256=current, matches=current == record["sha256"]))
    cases = []
    for task in TASKS:
        rows = sorted((r for r in direct if r["task"] == task), key=lambda r: (r["variant"] != "standard", r["seeds"]["layout_id"]))
        if len(rows) != 5:
            raise ValueError(f"Expected five published Direct cases for {task}")
        for row in rows:
            runtime_task = task + ("_random" if row["variant"] == "random" else "")
            seeds = row["seeds"]
            layout = layout_files(robodojo, runtime_task, seeds["eval_seed"])[seeds["layout_id"]]
            record = dict(case_id=row["case_id"], task=task, runtime_task=runtime_task, variant=row["variant"],
                          seeds=seeds, native_horizon=row["limit"], control_dt=row["dt"],
                          layout=dict(path=str(layout.relative_to(robodojo)), sha256=digest(layout)),
                          prior_direct=row)
            prior = historical_cases.get(row["case_id"])
            if prior is None:
                raise ValueError(f"No historical asset identity for {row['case_id']}")
            record["historical_layout_sha256"] = prior["layout"]["sha256"]
            record["matches_historical_layout"] = record["layout"]["sha256"] == prior["layout"]["sha256"]
            if not record["matches_historical_layout"]:
                raise ValueError(f"Current layout differs from historical fixture: {row['case_id']}")
            support = prior.get("native_support_trajectories", [])
            record["native_support_trajectories"] = []
            for item in support:
                actual = digest(robodojo / item["path"])
                if actual != item["sha256"]:
                    raise ValueError(f"Native support asset differs: {item['path']}")
                record["native_support_trajectories"].append(item)
            cases.append(record)
    panel = dict(schema="agent_action.published_direct_panel.v1", status="prepared_not_run",
                 scope="published_ten_tasks_five_cases_each", task_order=list(TASKS), cases=cases,
                 native_source_comparison=native_sources,
                 sources={str(public): digest(public), str(reference / "report_web/data.json"): digest(reference / "report_web/data.json")},
                 comparison="Pair case_id, seeds, layout hash and native horizon with prior Direct. Model, context and adapter differences remain explicit.",
                 incomplete_policy="Keep prior and new incomplete attempts separate; never replace missing native scores with zero.")
    panel["panel_sha256"] = hashlib.sha256(json.dumps(panel, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return panel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--reference", type=Path, default=root.parent / "GPT-as-Policy")
    parser.add_argument("--robodojo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    panel = freeze(args.reference.resolve(), args.robodojo.resolve())
    with args.output.open("x") as stream:
        json.dump(panel, stream, ensure_ascii=False, indent=2)
    print(f"Prepared {len(panel['cases'])} cases across {len(panel['task_order'])} tasks; all historical asset hashes match.")


if __name__ == "__main__":
    main()

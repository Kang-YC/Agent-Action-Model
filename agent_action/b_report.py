"""Evaluator-only B-line summaries; native labels never enter agent observations."""

import json
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def summarize(output: Path, *, status: str, sim_output: Path | None = None) -> dict:
    robot = output / "robot"
    packets = sorted(robot.glob("observation_*/observation.json"))
    latest = read_json(packets[-1]) if packets else None
    requests = (
        [
            json.loads(line)
            for line in (output / "requests.jsonl").read_text().splitlines()
        ]
        if (output / "requests.jsonl").exists()
        else []
    )
    completed = [r for r in requests if r["status"] == "completed"]
    attempted = len(list(output.glob("request_*.input.json.gz")))
    native = read_json(sim_output / "evaluation_outcome.json") if sim_output else None
    valid = bool(
        native and native.get("valid_for_success_rate") and native.get("complete")
    )
    budget_statuses = {
        "control_budget",
        "token_budget",
        "LimitsExceeded",
        "TimeExceeded",
    }
    classification = (
        "native_completed"
        if valid
        else "context_exhausted"
        if status == "context_limit"
        else "budget_censored"
        if status in budget_statuses
        else "model_stopped"
        if status == "Submitted"
        else "infrastructure_error"
    )
    return dict(
        status=status,
        classification=classification,
        last_observation=latest,
        native_outcome=native,
        native_complete=bool(native and native.get("complete")),
        scored=valid,
        native_success=native.get("native_success") if valid else None,
        native_score=native.get("native_score") if valid else None,
        attempted_model_requests=attempted,
        completed_model_requests=len(completed),
        error_model_requests=sum(r["status"] == "error" for r in requests),
        requests_without_usage=attempted - sum(bool(r.get("usage")) for r in completed),
        total_tokens=sum(
            (r.get("usage") or {}).get("total_tokens", 0) for r in completed
        ),
        model_latency_seconds=sum(r["latency_seconds"] for r in completed),
    )

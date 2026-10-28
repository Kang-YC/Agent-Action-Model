"""Read-only A/B development comparison from captured run artifacts.

python -m agent_action.ab_report --a-run artifacts/A --b-run artifacts/B --output artifacts/AB
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import time

from agent_action.service import process_identity


class Reader:
    def __init__(self):
        self.warnings = []

    def json(self, path):
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            self.warnings.append(f"{path}: {type(error).__name__}; unavailable in this snapshot")
            return None

    def lines(self, path):
        if not path.exists():
            return []
        result = []
        for index, line in enumerate(path.read_text().splitlines(keepends=True)):
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                self.warnings.append(f"{path}:{index + 1}: incomplete or invalid JSONL row omitted")
        return result


def model_metrics(root, route, reader):
    folder = root / ("model_requests" if route == "A" else "controller")
    rows = reader.lines(folder / "requests.jsonl")
    attempted, completed, errors = set(), {}, set()
    for path in folder.glob("*.input.json.gz"):
        stem = path.name.removesuffix(".input.json.gz")
        attempted.add(stem if route == "A" else str(int(stem.removeprefix("request_"))))
    for row in rows:
        identifier = str(row.get("id") if route == "A" else row.get("index"))
        event = row.get("event") if route == "A" else row.get("status")
        if event in ("request", "response", "completed", "error"):
            attempted.add(identifier)
        if event in ("response", "completed"):
            completed[identifier] = row
        elif event == "error":
            errors.add(identifier)
    usage = [r["usage"] for r in completed.values()
             if isinstance(r.get("usage"), dict) and r["usage"].get("total_tokens") is not None]
    latencies = [r.get("elapsed_s" if route == "A" else "latency_seconds") for r in completed.values()]
    latencies = [v for v in latencies if isinstance(v, (int, float))]
    return dict(attempted=len(attempted), completed=len(completed), errors=len(errors),
                in_flight_or_unresolved=len(attempted - completed.keys() - errors),
                requests_without_usage=len(attempted) - len(usage),
                recorded_total_tokens=sum(u["total_tokens"] for u in usage) if usage else None,
                completed_request_latency_seconds=sum(latencies) if latencies else None,
                latency_scope="Client/bridge elapsed time, including service queue; not GPU generation time")


def action_metrics(root, route, reader):
    controller = root / "controller"
    reasons = Counter()
    if route == "A":
        history = reader.json(controller / "history.json")
        accepted = sum(h.get("executed_steps", 0) > 0 for h in history) if isinstance(history, list) else None
        progress = reader.json(controller / "progress.json") or {}
        steps = progress.get("step_id")
        for path in (controller / "codex_workspace").glob("call_*_result.json"):
            request = reader.json(path.with_name(path.name.replace("_result.json", "_request.json"))) or {}
            if request.get("tool") != "robodojo_act":
                continue
            result = reader.json(path) or {}
            if result.get("error_type") == "recoverable_tool_input" and result.get("no_execution"):
                reasons[result.get("error", "unspecified")] += 1
        other_errors, pending = None, None
    else:
        actions = [reader.json(p) for p in sorted((controller / "robot").glob("action_*.json"))]
        actions = [a for a in actions if a]
        accepted = sum(a.get("status") == "acknowledged" for a in actions)
        pending = sum(a.get("status") != "acknowledged" for a in actions)
        observations = sorted((controller / "robot").glob("observation_*/observation.json"))
        packet = reader.json(observations[-1]) if observations else None
        steps = packet.get("step_id") if packet else None
        trajectory = reader.json(controller / "trajectory.json") or {}
        other_errors = 0
        for message in trajectory.get("messages", []):
            extra = message.get("extra", {})
            if message.get("role") != "tool" or not extra.get("returncode"):
                continue
            text = extra.get("output", "")
            last_line = text.strip().splitlines()[-1] if text.strip() else "unknown tool error"
            # Count only known pre-execution validation failures, not arbitrary
            # Python ValueError or an uncertain RPC/receipt failure.
            if (("agent_action/robot.py" in text and "in validate" in text)
                    or "ValueError: Action exceeds remaining control budget:" in text):
                reasons[last_line] += 1
            else:
                other_errors += 1
    rejected = sum(reasons.values())
    denominator = accepted + rejected if accepted is not None else None
    return dict(control_steps=steps, acknowledged_action_chunks=accepted,
                known_preexecution_rejections=rejected, rejection_reasons=dict(reasons),
                rejection_rate=rejected / denominator if denominator else None,
                rejection_rate_denominator="Acknowledged action chunks + known pre-execution rejections; excludes non-action cells, unresolved actions and other tool errors",
                other_tool_errors=other_errors, unresolved_action_records=pending)


def lifecycle(root, route, summary, reader, now):
    launch_path = Path(str(root) + (".launch.json" if route == "A" else ".state.json"))
    launch = reader.json(launch_path) or {}
    if summary is not None:
        phase = "finalized"
    elif launch.get("host") != socket.gethostname():
        phase = "unfinalized_liveness_unverified"
    else:
        identity = process_identity(launch.get("pid", -1))
        # PID alone is insufficient on a shared workspace. Check the owning
        # host and a command argument containing this exact run path/name.
        alive = identity and any(str(root) == arg or
                                 str(root) + ".supervisor.py" == arg or
                                 str(Path("artifacts") / (root.name + ".supervisor.py")) == arg
                                 for arg in identity["argv"])
        phase = "running_verified" if alive else "stopped_without_summary"
    start = launch.get("started_at")
    if start is None and launch.get("started_at_utc"):
        start = datetime.fromisoformat(launch["started_at_utc"]).timestamp()
    end = ((root / "summary.json") if route == "A" else (root / "controller/summary.json"))
    elapsed = max(0, (end.stat().st_mtime if summary is not None else now) - start) if start else None
    return dict(phase=phase, finalized=summary is not None, host=launch.get("host"),
                launch_elapsed_seconds=elapsed, launch_elapsed_scope="Launch through snapshot, or final summary mtime; includes startup/cleanup"), launch


def video_info(root, finalized):
    path = root / "sim/sensors.mp4"
    result = dict(path=str(path), status="not_checked_while_unfinalized")
    if not finalized:
        return result
    if not path.exists():
        return dict(path=str(path), status="missing")
    try:
        probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                                "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", str(path)],
                               text=True, capture_output=True, timeout=20)
        streams = json.loads(probe.stdout).get("streams", []) if probe.returncode == 0 else []
        return dict(path=str(path), status="readable" if streams else "unreadable", streams=streams)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        return dict(path=str(path), status="probe_error", error=str(error))


def collect(root, route, now):
    reader = Reader()
    summary_path = root / ("summary.json" if route == "A" else "controller/summary.json")
    summary = reader.json(summary_path)
    lifecycle_info, launch = lifecycle(root, route, summary, reader, now)
    native = reader.json(root / "sim/evaluation_outcome.json")
    if native is None and summary:
        native = summary.get("native_outcome")
    eligible = bool(native and native.get("complete") and native.get("valid_for_success_rate"))
    # A running native success flag, or a model's Submitted/ReturnAnswer, is
    # never substituted for the native evaluator's final eligible labels.
    result = dict(root=str(root), route=route, **lifecycle_info,
                  summary_status=(summary or {}).get("status"),
                  termination=(summary or {}).get("task_outcome") or (summary or {}).get("classification") or (summary or {}).get("status"),
                  error_type=(summary or {}).get("error_type"), error=(summary or {}).get("error"),
                  failure_category=(summary or {}).get("failure_category"),
                  native_complete=bool(native and native.get("complete")), scored=eligible,
                  native_success=native.get("native_success") if eligible else None,
                  native_score=native.get("native_score") if eligible else None,
                  native_outcome=native, model=model_metrics(root, route, reader),
                  actions=action_metrics(root, route, reader),
                  reported_wall_seconds=(summary or {}).get("wall_seconds"),
                  reported_wall_scope="A orchestrator" if route == "A" else "B controller",
                  sources=dict(summary=str(summary_path), native=str(root / "sim/evaluation_outcome.json"),
                               requests=str(root / ("model_requests/requests.jsonl" if route == "A" else "controller/requests.jsonl"))),
                  warnings=reader.warnings)
    if summary and (summary.get("last_observation") or {}).get("step_id") is not None:
        result["actions"]["control_steps"] = summary["last_observation"]["step_id"]
    if summary and route == "A":
        final_step = (native or {}).get("native_control_steps")
        if final_step is None:
            final_step = summary.get("last_acknowledged_control_step")
        if final_step is None:
            final_step = (summary.get("result") or {}).get("step_id")
        if final_step is not None:
            result["actions"]["control_steps"] = final_step
    result["video"] = video_info(root, result["finalized"])
    streams = result["video"].get("streams", [])
    steps = result["actions"]["control_steps"]
    result["video"]["frames_equal_steps_plus_initial"] = (
        int(streams[0]["nb_read_frames"]) == steps + 1
        if streams and streams[0].get("nb_read_frames", "").isdigit() and steps is not None else None)
    reset = reader.json(root / "sim/reset.json") or {}
    if route == "A":
        plan = (reader.json(Path(str(root) + ".plan.json")) or {}).get("plan", {})
        model_config = reader.json(root / "base_model.json")
    else:
        manifest = reader.json(root / "controller/manifest.json") or {}
        plan = launch.get("plan", {})
        model_config = manifest.get("model")
    result["protocol"] = dict(plan=plan, metadata=reset.get("metadata", {}), model_config=model_config,
                              resolved_config=reader.json(root / "sim/resolved_config.json"),
                              initial_fingerprint=reader.json(root / "sim/initial_observation_fingerprint.json"))
    return result


def compare_protocol(a, b):
    checks = []
    for group, fields in (("metadata", ("task", "layout_id", "eval_seed", "max_episode_steps", "control_dt", "frame", "eef_link", "robot_adapter", "gripper_semantics", "cameras")),
                          ("model_config", ("checkpoint", "served_model_name", "dtype", "max_model_len", "temperature", "top_p", "max_completion_tokens", "enable_thinking", "max_image_pixels", "max_images", "vllm_version")),
                          ("plan", ("max_control_steps", "max_total_tokens", "wall_seconds"))):
        for field in fields:
            left = (a["protocol"].get(group) or {}).get(field)
            right = (b["protocol"].get(group) or {}).get(field)
            checks.append(dict(field=f"{group}.{field}", a=left, b=right,
                               equal=left == right if left is not None and right is not None else None))
    left = a["protocol"]["plan"].get("max_decisions")
    right = b["protocol"]["plan"].get("max_turns")
    checks.append(dict(field="plan.extra_model_turn_limit", a=left, b=right,
                       equal=left == right if left is not None and right is not None else None))
    for group in ("sim", "scene", "camera", "robot", "eval_cfg", "deploy_cfg", "task_env"):
        left = (a["protocol"].get("resolved_config") or {}).get(group)
        right = (b["protocol"].get("resolved_config") or {}).get(group)
        checks.append(dict(field=f"resolved_config.{group}", equal=left == right if left is not None and right is not None else None))
    fingerprints = {}
    fa = (a["protocol"].get("initial_fingerprint") or {}).get("fields", {})
    fb = (b["protocol"].get("initial_fingerprint") or {}).get("fields", {})
    for field in sorted(fa.keys() | fb.keys()):
        fingerprints[field] = fa[field] == fb[field] if field in fa and field in fb else None
    return dict(checks=checks, matched_known_conditions=all(c["equal"] is True for c in checks),
                initial_observation_fields_equal=fingerprints,
                caveat="Single development pair; differing tools, static geometry/calibration access, prompts and history management. RGB is not asserted pixel-identical. No causal ranking or success-rate estimate.")


def build_report(a_root, b_root, now=None):
    now = time.time() if now is None else now
    a, b = collect(a_root.resolve(), "A", now), collect(b_root.resolve(), "B", now)
    return dict(schema="agent_action.ab_development.v1", as_of_unix=now,
                snapshot_is_atomic=False, formal_evaluation=False,
                runs=dict(A=a, B=b), comparison=compare_protocol(a, b))


def markdown(report):
    def cell(value):
        if value is None:
            return "—"
        return (f"{value:.2f}" if isinstance(value, float) else str(value)).replace("|", "\\|").replace("\n", " ")

    rows = [("State", lambda r: r["phase"]), ("Termination", lambda r: r["termination"]),
            ("Error type", lambda r: r["error_type"]), ("Failure category", lambda r: r["failure_category"]),
            ("Native scored", lambda r: r["scored"]), ("Native success", lambda r: r["native_success"]),
            ("Native score", lambda r: r["native_score"]), ("Control steps", lambda r: r["actions"]["control_steps"]),
            ("Acknowledged action chunks", lambda r: r["actions"]["acknowledged_action_chunks"]),
            ("Known pre-execution rejections", lambda r: r["actions"]["known_preexecution_rejections"]),
            ("Resolved action rejection rate", lambda r: r["actions"]["rejection_rate"]),
            ("Model requests attempted / completed", lambda r: f"{r['model']['attempted']} / {r['model']['completed']}"),
            ("Requests without usage", lambda r: r["model"]["requests_without_usage"]),
            ("Recorded tokens (partial if usage missing)", lambda r: r["model"]["recorded_total_tokens"]),
            ("Completed request latency incl. queue (s)", lambda r: r["model"]["completed_request_latency_seconds"]),
            ("Launch elapsed incl. startup/cleanup (s)", lambda r: r["launch_elapsed_seconds"]),
            ("Video", lambda r: r["video"]["status"]),
            ("Video frames = control steps + 1", lambda r: r["video"]["frames_equal_steps_plus_initial"])]
    stamp = datetime.fromtimestamp(report["as_of_unix"], timezone.utc).isoformat()
    lines = ["# A/B development comparison", "", f"Snapshot: {stamp}", "",
             report["comparison"]["caveat"], "", "| Metric | A | B |", "|---|---|---|"]
    for title, fn in rows:
        lines.append(f"| {title} | {cell(fn(report['runs']['A']))} | {cell(fn(report['runs']['B']))} |")
    lines += ["", "Missing labels remain missing. Running/unfinalized trials are not failures. "
              "Rejection rate uses acknowledged chunks + known pre-execution rejections; other tool errors are excluded. "
              "Model calls include analysis and non-action tools. Latency includes queueing; wall scopes and tools differ.",
              "", "## Matched conditions", "", "| Condition | Equal |", "|---|---|"]
    lines += [f"| {c['field']} | {cell(c['equal'])} |" for c in report["comparison"]["checks"]]
    lines += ["", "## Evidence", ""]
    for route, run in report["runs"].items():
        lines += [f"- {route}: [{run['root']}]({run['root']})",
                  f"- {route} rejection reasons: {json.dumps(run['actions']['rejection_reasons'], ensure_ascii=False)}"]
        lines += [f"- Warning: {w}" for w in run["warnings"]]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-run", required=True, type=Path)
    parser.add_argument("--b-run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--watch", action="store_true", help="Refresh until both runs finalize or are confirmed stopped")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()
    if args.interval < 1:
        parser.error("interval must be positive")
    output = args.output.resolve()
    if any(output.is_relative_to(root.resolve()) for root in (args.a_run, args.b_run)):
        parser.error("Output must be outside both input run directories")
    output.mkdir(parents=True, exist_ok=True)
    while True:
        report = build_report(args.a_run, args.b_run)
        for name, content in (("comparison.json", json.dumps(report, ensure_ascii=False, indent=2)),
                              ("comparison.md", markdown(report))):
            target = output / name
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(content)
            temporary.replace(target)
        if not args.watch or all(r["phase"] in ("finalized", "stopped_without_summary") for r in report["runs"].values()):
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

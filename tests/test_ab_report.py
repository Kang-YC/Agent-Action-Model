import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from agent_action.ab_report import build_report, main, markdown


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def log(path, rows, suffix=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows) + suffix)


def test_live_cost_and_rejection_denominators_do_not_conflate_model_calls(tmp_path):
    a, b = tmp_path / "A", tmp_path / "B"
    write(a / "controller/progress.json", dict(step_id=5))
    write(a / "controller/history.json", [dict(executed_steps=5)])
    calls = a / "controller/codex_workspace"
    write(calls / "call_0001_request.json", dict(tool="robodojo_act"))
    write(calls / "call_0001_result.json", dict(error_type="recoverable_tool_input", no_execution=True, error="bound"))
    # A rejected non-action tool must not inflate the action rejection rate.
    write(calls / "call_0002_request.json", dict(tool="robodojo_start"))
    write(calls / "call_0002_result.json", dict(error_type="recoverable_tool_input", no_execution=True))
    log(a / "model_requests/requests.jsonl", [
        dict(event="request", id="x"), dict(event="response", id="x", usage=dict(total_tokens=20), elapsed_s=3),
        dict(event="request", id="y"), dict(event="error", id="y")])
    write(b / "controller/robot/observation_0001/observation.json", dict(step_id=5))
    write(b / "controller/robot/action_0001.json", dict(status="acknowledged", end_step=5))
    write(b / "controller/robot/action_0002.json", dict(status="uncertain"))
    write(b / "controller/trajectory.json", dict(messages=[
        dict(role="tool", extra=dict(returncode=1, output='agent_action/robot.py in validate\nValueError: bound')),
        dict(role="tool", extra=dict(returncode=1, output='SyntaxError: bad code'))]))
    log(b / "controller/requests.jsonl", [
        dict(index=1, status="completed", usage=dict(total_tokens=10), latency_seconds=4),
        dict(index=2, status="completed", usage=None, latency_seconds=5)], suffix='{"index":3')
    write(b / "sim/evaluation_outcome.json", dict(complete=False, valid_for_success_rate=False, native_success=False, native_score=0))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    report = build_report(a, b, now=1000)
    assert {p: p.read_bytes() for p in before} == before
    for route in ("A", "B"):
        run = report["runs"][route]
        assert run["actions"]["control_steps"] == 5
        assert run["actions"]["rejection_rate"] == 0.5
        assert run["actions"]["known_preexecution_rejections"] == 1
        assert run["model"]["attempted"] == 2
        assert run["model"]["requests_without_usage"] == 1
        assert run["native_success"] is run["native_score"] is None
        assert run["video"]["status"] == "not_checked_while_unfinalized"
    assert report["runs"]["A"]["model"]["recorded_total_tokens"] == 20
    assert report["runs"]["B"]["model"]["recorded_total_tokens"] == 10
    assert report["runs"]["B"]["actions"]["other_tool_errors"] == 1
    assert report["runs"]["B"]["actions"]["unresolved_action_records"] == 1
    assert report["runs"]["B"]["warnings"]
    assert not report["comparison"]["matched_known_conditions"]
    assert "partial if usage missing" in markdown(report)


@pytest.mark.parametrize("eligible", [True, False])
def test_only_eligible_final_native_labels_are_scored(tmp_path, eligible):
    a, b = tmp_path / "A", tmp_path / "B"
    write(a / "summary.json", dict(status="completed", task_outcome="success"))
    write(b / "controller/summary.json", dict(status="Submitted", classification="model_stopped"))
    for root in (a, b):
        write(root / "sim/evaluation_outcome.json", dict(complete=True,
              valid_for_success_rate=eligible, native_success=False, native_score=0))
    report = build_report(a, b, now=1000)
    for run in report["runs"].values():
        assert run["phase"] == "finalized"
        assert run["scored"] == eligible
        assert run["native_success"] is (False if eligible else None)
        assert run["native_score"] == (0 if eligible else None)
        assert run["model"]["recorded_total_tokens"] is None
        assert run["video"]["status"] == "missing"


def test_liveness_checks_host_and_command_instead_of_pid_alone(tmp_path, monkeypatch):
    a, b = tmp_path / "A", tmp_path / "B"
    write(Path(str(a) + ".launch.json"), dict(host=socket.gethostname(), pid=123, started_at=900))
    write(Path(str(b) + ".state.json"), dict(host="different-host", pid=123, started_at=900))
    monkeypatch.setattr("agent_action.ab_report.process_identity", lambda pid: dict(argv=[str(a)]))
    report = build_report(a, b, now=1000)
    assert report["runs"]["A"]["phase"] == "running_verified"
    assert report["runs"]["A"]["launch_elapsed_seconds"] == 100
    assert report["runs"]["B"]["phase"] == "unfinalized_liveness_unverified"
    monkeypatch.setattr("agent_action.ab_report.process_identity", lambda pid: dict(argv=["unrelated"]))
    assert build_report(a, b)["runs"]["A"]["phase"] == "stopped_without_summary"


def test_report_rejects_output_inside_input_run(tmp_path, monkeypatch):
    a, b = tmp_path / "A", tmp_path / "B"
    monkeypatch.setattr("sys.argv", ["ab_report", "--a-run", str(a), "--b-run", str(b),
                                     "--output", str(b / "report")])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    assert not b.exists()


def test_final_steps_override_stale_progress_and_video_is_checked_only_after_summary(tmp_path, monkeypatch):
    a, b = tmp_path / "A", tmp_path / "B"
    write(a / "controller/progress.json", dict(step_id=75))
    write(a / "summary.json", dict(status="controller_error", last_acknowledged_control_step=80))
    write(b / "controller/robot/observation_0001/observation.json", dict(step_id=5))
    video = b / "sim/sensors.mp4"
    video.parent.mkdir(parents=True)
    video.touch()
    calls = []

    def probe(*args, **kwargs):
        calls.append(args[0])
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(streams=[dict(
            width=1920, height=360, nb_read_frames="6")])))

    monkeypatch.setattr("agent_action.ab_report.subprocess.run", probe)
    live = build_report(a, b)
    assert live["runs"]["A"]["actions"]["control_steps"] == 80
    assert live["runs"]["A"]["termination"] == "controller_error"
    assert not calls
    write(b / "controller/summary.json", dict(status="native_terminal"))
    final = build_report(a, b)
    assert len(calls) == 1
    assert final["runs"]["B"]["video"]["frames_equal_steps_plus_initial"] is True


def test_operator_budget_revision_preserves_actual_steps_and_raw_status(tmp_path):
    a, b = tmp_path / "A", tmp_path / "B"
    write(b / "controller/summary.json", dict(status="infrastructure_error", last_observation=dict(step_id=620)))
    write(Path(str(b) + ".budget-revision.json"), dict(stop_confirmed=True, requested_limit=400))
    write(Path(str(b) + ".development-assessment.json"), dict(
        development_outcome="failure_400_step_limit", development_success=False, budget_steps=400))
    report = build_report(a, b)
    run = report["runs"]["B"]
    assert run["termination"] == "operator_budget_revision"
    assert run["summary_status"] == "infrastructure_error"
    assert run["actions"]["control_steps"] == 620
    assert run["native_score"] is None
    assert run["development_assessment"]["development_success"] is False
    assert "failure_400_step_limit" in markdown(report)
    assert "actual executed steps are not rewritten" in markdown(report)

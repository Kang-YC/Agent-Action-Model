import copy
import hashlib
import json
from pathlib import Path
import socket

import pytest

from agent_action.b_case import prepare_case, verify_prepared
from agent_action.b_sequence import prerequisite_status


def fixture(tmp_path):
    # Real frozen identity schema, with local substitute fixture bytes.
    from hybrid_rollout.robodojo.evaluation import canonical_sha256
    panel = json.loads(Path("configs/a_published_ten_task_panel.json").read_text())
    native = json.loads(Path("configs/a_native_panel60_v1.json").read_text())
    cid = "classify_objects_by_language__standard__g0__l0"
    layout = dict(path="layout.json", sha256=hashlib.sha256(b"{}").hexdigest())
    (tmp_path / "layout.json").write_text("{}")
    for case in panel["cases"]:
        if case["case_id"] == cid:
            case["layout"] = layout
    for case in native["cases"]:
        if case["case_id"] == cid:
            case["layout"] = layout
    panel["panel_sha256"] = hashlib.sha256(json.dumps(
        {k:v for k,v in panel.items() if k != "panel_sha256"}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    native["panel_sha256"] = canonical_sha256({k:v for k,v in native.items() if k != "panel_sha256"})
    public_path, native_path = tmp_path / "public.json", tmp_path / "native.json"
    public_path.write_text(json.dumps(panel))
    native_path.write_text(json.dumps(native))
    return public_path, native_path, cid


def test_native_binding_and_budget_cannot_be_silently_changed(tmp_path, monkeypatch):
    panel, native, cid = fixture(tmp_path)
    checked = []
    monkeypatch.setattr("hybrid_rollout.robodojo.evaluation.verify_assets", lambda *args: checked.append(args))
    output = tmp_path / "run"
    record = prepare_case(panel, native, cid, tmp_path, output)
    assert not output.exists()  # preparation never starts a simulator
    assert record["plan"]["max_control_steps"] == 1100
    assert record["environment"]["B_LINE_EVAL_SEED"] == "0"
    verify_prepared(record)
    assert len(checked) == 2
    altered = copy.deepcopy(record)
    altered["argv"][altered["argv"].index("--max-control-steps") + 1] = "400"
    with pytest.raises(ValueError, match="command differs"):
        verify_prepared(altered)
    altered = copy.deepcopy(record)
    altered["plan"]["native_control_horizon"] = altered["plan"]["max_control_steps"] = 400
    with pytest.raises(ValueError, match="published native limit"):
        verify_prepared(altered)
    with pytest.raises(FileExistsError):
        prepare_case(panel, native, cid, tmp_path, output)


def test_case_identity_tampering_stops_launch(tmp_path, monkeypatch):
    panel, native, cid = fixture(tmp_path)
    monkeypatch.setattr("hybrid_rollout.robodojo.evaluation.verify_assets", lambda *args: None)
    record = prepare_case(panel, native, cid, tmp_path, tmp_path / "run")
    path = Path(record["environment"]["B_LINE_CASE_FILE"])
    case = json.loads(path.read_text())
    case["identity"]["layout_id"] = 1
    path.write_text(json.dumps(case))
    with pytest.raises(ValueError, match="native identity changed"):
        verify_prepared(record)


def test_native_failure_allows_queue_but_infrastructure_failure_does_not(tmp_path):
    run = tmp_path / "prerequisite"
    (run / "controller").mkdir(parents=True)
    state = Path(str(run) + ".state.json")
    state.write_text(json.dumps(dict(host=socket.gethostname(), status="finished", pid=123)))
    summary = run / "controller/summary.json"
    summary.write_text(json.dumps(dict(native_outcome=dict(complete=True,
        valid_for_success_rate=True, native_success=False))))
    assert prerequisite_status(run) == "ready"
    summary.write_text(json.dumps(dict(status="infrastructure_error",
        native_outcome=dict(complete=False,valid_for_success_rate=False))))
    assert prerequisite_status(run) == "prerequisite_not_native_complete"

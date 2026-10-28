import json
from pathlib import Path

import pytest

from agent_action.b_panel import digest, prepare


def fixture(tmp_path):
    panel = json.loads(Path("configs/a_published_ten_task_panel.json").read_text())
    panel["cases"] = [c for c in panel["cases"] if c["runtime_task"] == "classify_objects"][:2]
    assert panel["cases"][0]["seeds"]["layout_id"] == 0
    import hashlib
    for i, case in enumerate(panel["cases"]):
        path = tmp_path / f"layout{i}.json"
        path.write_text(json.dumps(dict(layout=i)))
        case["layout"] = dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        case["native_support_trajectories"] = []
    panel["panel_sha256"] = digest({k: v for k, v in panel.items() if k != "panel_sha256"})
    run = tmp_path / "development"
    (run / "controller").mkdir(parents=True)
    (run / "controller/manifest.json").write_text(json.dumps(dict(
        arguments=dict(history_turns=8), model=dict(checkpoint="fixed"))))
    exclusions = json.loads(Path("configs/b_development_exclusions.json").read_text())
    return panel, exclusions, run


def test_proposal_excludes_development_and_never_emits_launches_or_scores(tmp_path):
    panel, exclusions, run = fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    report = prepare(panel, exclusions, tmp_path, run)
    assert {p: p.read_bytes() for p in before} == before
    assert report["candidate_cases"] == report["excluded_cases"] == 1
    assert report["status"] == "draft_not_frozen"
    assert not report["launches_processes"] and report["launchable_cases"] == 0
    assert all(c["executable_command"] is None for c in report["cases"])
    assert report["cases"][1]["proposed_controller_arguments"]["seed"] == 1
    assert report["cases"][1]["required_native_identity"]["layout_sha256"] == panel["cases"][1]["layout"]["sha256"]
    assert "prior_direct" not in json.dumps(report) and "native_success" not in json.dumps(report)


def test_changed_layout_or_panel_is_rejected(tmp_path):
    panel, exclusions, run = fixture(tmp_path)
    (tmp_path / "layout0.json").write_text("changed")
    with pytest.raises(ValueError, match="asset mismatch"):
        prepare(panel, exclusions, tmp_path, run)
    panel["cases"][0]["native_horizon"] = 1
    with pytest.raises(ValueError, match="panel hash mismatch"):
        prepare(panel, exclusions, tmp_path, run)


def test_unknown_history_protocol_requires_review(tmp_path):
    panel, exclusions, run = fixture(tmp_path)
    path = run / "controller/manifest.json"
    manifest = json.loads(path.read_text())
    manifest["arguments"]["history_turns"] = 0
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="window-8"):
        prepare(panel, exclusions, tmp_path, run)


def test_runtime_variant_is_preserved_and_exclusion_does_not_leak_across_variants(tmp_path):
    panel, exclusions, run = fixture(tmp_path)
    case = panel["cases"][0]
    case["runtime_task"] = "classify_objects_random"
    case["variant"] = "random"
    panel["panel_sha256"] = digest({k: v for k, v in panel.items() if k != "panel_sha256"})
    report = prepare(panel, exclusions, tmp_path, run)
    assert report["candidate_cases"] == 2
    assert report["cases"][0]["proposed_controller_arguments"]["task"] == "classify_objects_random"

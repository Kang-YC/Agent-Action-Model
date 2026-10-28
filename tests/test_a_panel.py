import hashlib
import json
from pathlib import Path

import pytest

from agent_action.a_line import published_case_plan, native_case_selection
from agent_action.a_panel import prepare


def fixture(tmp_path):
    panel = json.loads(Path('configs/a_published_ten_task_panel.json').read_text())
    panel['cases'] = panel['cases'][:1]
    asset = tmp_path / 'layout.json'
    asset.write_text('{}')
    panel['cases'][0]['layout'] = dict(path=asset.name, sha256=hashlib.sha256(asset.read_bytes()).hexdigest())
    panel['cases'][0]['native_support_trajectories'] = []
    panel['panel_sha256'] = hashlib.sha256(json.dumps({k: v for k, v in panel.items() if k != 'panel_sha256'}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    runs = tmp_path / 'runs'
    runs.mkdir()
    native = json.loads(Path('configs/a_native_panel60_v1.json').read_text())
    native['cases'][0]['layout'] = panel['cases'][0]['layout']
    native['panel_sha256'] = hashlib.sha256(json.dumps({k: v for k, v in native.items() if k != 'panel_sha256'}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    return panel, runs, native


def attempt(panel, runs, name, native, complete=False, success=False):
    run = runs / name
    (run / 'sim').mkdir(parents=True)
    plan = published_case_plan(panel, panel['cases'][0]['case_id'])
    identity = native_case_selection(plan, native)['identity']
    run.with_name(run.name + '.plan.json').write_text(json.dumps(dict(plan=plan, evaluation_identity=identity)))
    (run / 'manifest.json').write_text(json.dumps(dict(evaluation_identity=identity)))
    (run / 'summary.json').write_text(json.dumps(dict(status='completed' if complete else 'simulator_error')))
    (run / 'sim/evaluation_outcome.json').write_text(json.dumps(dict(evaluation_case=identity, complete=complete, valid_for_success_rate=complete,
        native_success=success if complete else None, native_score=0.5 if complete else None, native_control_steps=1000)))
    return run


def test_pending_plan_checks_assets_without_creating_runs(tmp_path):
    panel, runs, native = fixture(tmp_path)
    report = prepare(panel, tmp_path, runs, native_panel=native)
    assert report['pending_cases'] == 1
    assert '--case-id' in report['cases'][0]['next_command']
    assert not list(runs.iterdir())
    (tmp_path / 'layout.json').write_text('changed')
    with pytest.raises(ValueError, match='asset mismatch'):
        prepare(panel, tmp_path, runs, native_panel=native)


def test_infrastructure_attempt_remains_missing_and_requires_review(tmp_path):
    panel, runs, native = fixture(tmp_path)
    name = panel['cases'][0]['case_id'] + '--attempt-001'
    attempt(panel, runs, name, native)
    report = prepare(panel, tmp_path, runs, native_panel=native)
    case = report['cases'][0]
    assert report['complete_cases'] == 0
    assert case['state'] == 'needs_review'
    assert case['attempts'][0]['native_score'] is None
    assert '--attempt-002' in case['next_command']


def test_native_failure_completes_case_and_is_not_retried(tmp_path):
    panel, runs, native = fixture(tmp_path)
    attempt(panel, runs, 'first', native, complete=True, success=False)
    report = prepare(panel, tmp_path, runs, native_panel=native)
    assert report['complete_cases'] == 1
    assert report['successful_cases'] == 0
    assert report['cases'][0]['next_command'] is None
    assert report['cases'][0]['result']['native_score'] == 0.5
    attempt(panel, runs, 'second', native, complete=True, success=True)
    with pytest.raises(ValueError, match='Multiple complete attempts'):
        prepare(panel, tmp_path, runs, native_panel=native)


def test_finalization_and_plan_identity_required(tmp_path):
    panel, runs, native = fixture(tmp_path)
    run = attempt(panel, runs, 'first', native, complete=True)
    (run / 'summary.json').unlink()
    assert prepare(panel, tmp_path, runs, native_panel=native)['complete_cases'] == 0
    snapshot = run.with_name(run.name + '.plan.json')
    saved = json.loads(snapshot.read_text())
    saved['plan']['max_control_steps'] = 1
    snapshot.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='plan differs'):
        prepare(panel, tmp_path, runs, native_panel=native)


@pytest.mark.parametrize('location', ['outcome', 'manifest', 'plan'])
def test_completed_score_without_matching_identity_is_rejected(tmp_path, location):
    panel, runs, native = fixture(tmp_path)
    run = attempt(panel, runs, 'wrong', native, complete=True, success=True)
    path, key = {
        'outcome': (run / 'sim/evaluation_outcome.json', 'evaluation_case'),
        'manifest': (run / 'manifest.json', 'evaluation_identity'),
        'plan': (run.with_name(run.name + '.plan.json'), 'evaluation_identity'),
    }[location]
    record = json.loads(path.read_text())
    record[key]['case_id'] = 'different-case'
    path.write_text(json.dumps(record))
    report = prepare(panel, tmp_path, runs, native_panel=native)
    assert report['complete_cases'] == report['successful_cases'] == 0
    assert report['cases'][0]['state'] == 'needs_review'
    assert report['cases'][0]['attempts'][0]['native_score'] is None

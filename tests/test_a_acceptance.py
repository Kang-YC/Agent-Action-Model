import gzip
import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

from agent_action.a_acceptance import audit


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def episode(tmp_path, final=True, success=False):
    run = tmp_path / 'run'
    controller = run / 'controller'
    history = []
    for decision in range(2):
        history.append(dict(decision=decision, start_tick=decision * 3, end_tick=(decision + 1) * 3, executed_steps=3))
        controller.mkdir(parents=True, exist_ok=True)
        np.savez(controller / f'execution_{decision:03d}.npz', actions=np.zeros((3, 14)), states=np.zeros((3, 14)))
    write(controller / 'history.json', history)
    write(controller / 'progress.json', dict(step_id=6, episode_id='episode'))
    write(controller / 'token_usage.json', dict(usage=dict(total=dict(totalTokens=100))))
    for tick in (0, 3, 6):
        image = controller / 'observations' / str(tick) / 'image.png'
        image.parent.mkdir(parents=True)
        image.write_bytes(b'fixture')
        write(image.with_name('observation.json'), dict(episode_id='episode', step_id=tick, images=[dict(path=str(image))]))
    requests = run / 'model_requests'
    requests.mkdir()
    (requests / 'one.input.json.gz').write_bytes(gzip.compress(json.dumps(dict(model_request=dict(messages=[dict(content=[dict(type='image_url')])]))).encode()))
    if final:
        write(run / 'summary.json', dict(status='completed'))
        write(controller / 'result.json', dict(reason='terminal', step_id=6))
        write(run / 'sim/evaluation_outcome.json', dict(complete=True, native_success=success, native_score=0.0 if not success else 1.0))
    return run


def video(monkeypatch, frames=7):
    monkeypatch.setattr('agent_action.a_acceptance.subprocess.run', lambda *a, **k: subprocess.CompletedProcess(a, 0,
        stdout=json.dumps(dict(streams=[dict(nb_read_frames=str(frames), width=1920, height=360)]))))


@pytest.mark.parametrize('success', [False, True])
def test_acceptance_does_not_depend_on_task_success(tmp_path, monkeypatch, success):
    run = episode(tmp_path, success=success)
    video(monkeypatch)
    report = audit(run)
    assert report['status'] == 'passed'
    assert report['task_result']['native_success'] is success
    assert report['task_success_required'] is False


def test_live_run_verifies_loop_but_defers_final_acceptance(tmp_path):
    run = episode(tmp_path, final=False)
    report = audit(run)
    assert report['status'] == 'incomplete'
    assert report['tool_loop_verified']
    assert report['video']['status'] == 'deferred_until_finalization'


def test_missing_execution_arrays_cannot_be_replaced_by_proposal(tmp_path, monkeypatch):
    run = episode(tmp_path)
    (run / 'controller/execution_001.npz').unlink()
    video(monkeypatch)
    report = audit(run)
    assert report['status'] == 'failed'
    assert not report['tool_loop_verified']


def test_infrastructure_exit_and_invalid_video_fail_acceptance(tmp_path, monkeypatch):
    run = episode(tmp_path)
    write(run / 'summary.json', dict(status='simulator_error'))
    video(monkeypatch)
    assert audit(run)['status'] == 'failed'
    write(run / 'summary.json', dict(status='completed'))
    video(monkeypatch, frames=6)
    assert audit(run)['status'] == 'failed'


def test_live_mixed_snapshot_is_incomplete_not_passed(tmp_path):
    run = episode(tmp_path, final=False)
    write(run / 'controller/progress.json', dict(step_id=3, episode_id='episode'))
    report = audit(run)
    assert report['status'] == 'incomplete'
    assert not report['tool_loop_verified']

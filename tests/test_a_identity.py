import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

from agent_action import a_line


def panels():
    return (json.loads(Path('configs/a_published_ten_task_panel.json').read_text()),
            json.loads(Path('configs/a_native_panel60_v1.json').read_text()))


def test_all_fifty_published_cases_map_to_native_identity():
    published, native = panels()
    for case in published['cases']:
        plan = a_line.published_case_plan(published, case['case_id'])
        selection = a_line.native_case_selection(plan, native)
        assert selection['identity']['case_id'] == case['case_id']
        assert selection['identity']['layout_sha256'] == case['layout']['sha256']
        assert selection['case']['native_support_trajectories'] == case['native_support_trajectories']
        changed = copy.deepcopy(plan)
        changed['layout_id'] += 1
        with pytest.raises(ValueError, match='identity differs'):
            a_line.native_case_selection(changed, native)


def test_case_launcher_forwards_frozen_native_identity_without_starting_gpu(tmp_path, monkeypatch):
    published, native = panels()
    published['cases'] = published['cases'][:1]
    asset = tmp_path / 'layout.json'
    asset.write_text('{}')
    layout = dict(path=asset.name, sha256=hashlib.sha256(asset.read_bytes()).hexdigest())
    published['cases'][0]['layout'] = layout
    native['cases'][0]['layout'] = layout
    published['panel_sha256'] = hashlib.sha256(json.dumps({k:v for k,v in published.items() if k != 'panel_sha256'}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    native['panel_sha256'] = hashlib.sha256(json.dumps({k:v for k,v in native.items() if k != 'panel_sha256'}, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    pub_path, native_path = tmp_path / 'published.json', tmp_path / 'native.json'
    pub_path.write_text(json.dumps(published))
    native_path.write_text(json.dumps(native))
    output = tmp_path / 'run'
    captured = []
    monkeypatch.setattr(sys, 'argv', ['a_line', '--panel', str(pub_path), '--native-panel', str(native_path),
        '--case-id', published['cases'][0]['case_id'], '--robodojo', str(tmp_path), '--output', str(output)])
    monkeypatch.setattr(a_line.os, 'execv', lambda executable, command: captured.append(command))
    a_line.main()
    command = captured[0]
    assert command[command.index('--eval-manifest') + 1] == str(native_path)
    case_file = Path(command[command.index('--case-file') + 1])
    selection = json.loads(case_file.read_text())
    record = json.loads(output.with_name('run.plan.json').read_text())
    assert selection['identity'] == record['evaluation_identity']
    assert record['plan']['case_id'] == selection['identity']['case_id']
    assert not output.exists()

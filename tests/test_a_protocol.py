import ast
from pathlib import Path
import shutil
from types import SimpleNamespace
import subprocess

import pytest

from agent_action.a_protocol import align_published_policy, REFERENCE_COMMIT, RUN_PATH

REFERENCE = Path(__file__).resolve().parents[2] / 'GPT-as-Policy'


def prompt_expression(source):
    return next(n.value for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Attribute) and t.attr == 'prompt' for t in n.targets))


def test_published_prompt_is_original_composition_and_has_no_extra_calibration(tmp_path):
    snapshot = tmp_path / 'snapshot'
    worker = snapshot / 'hybrid_rollout/luban_direct/worker.py'
    worker.parent.mkdir(parents=True)
    shutil.copy2(REFERENCE / 'hybrid_rollout/luban_direct/worker.py', worker)
    loop = snapshot / RUN_PATH
    loop.parent.mkdir(parents=True)
    loop.write_text('old loop')
    protocol = align_published_policy(snapshot, REFERENCE)
    source = worker.read_text()
    assert protocol['image_max_edge'] == 480
    assert 'build_calibration(source)' not in source
    assert 'robot_geometry' not in source
    assert 'Keep narration brief' not in source
    assert 'def _network_continue' not in source
    assert protocol['original_same_thread_network_recovery'] is True
    assert "self.image_max_edge = 'gpt_only', timeout, 480" in source
    assert "write_json(self.workspace/'tools.json', tool_specs('gpt_only'))" in source
    original = subprocess.check_output(['git', '-C', str(REFERENCE), 'show', f'{REFERENCE_COMMIT}:{RUN_PATH}'], text=True)
    assert loop.read_text() == original
    skill = tmp_path / 'skill'
    skill.mkdir()
    (skill / 'SKILL.md').write_text('original skill')
    teacher = tmp_path / 'teacher.md'
    teacher.write_text('original context with substituted model identity')
    agent = SimpleNamespace(agent_workspace=Path('/episode/agent'))
    actual = eval(compile(ast.Expression(prompt_expression(source)), '<adapted>', 'eval'),
                  dict(root=skill, teacher=teacher, self=agent))
    expected = eval(compile(ast.Expression(prompt_expression(original)), '<published>', 'eval'),
                    dict(skill='original skill', direct=True, context=teacher.read_text(), self=agent))
    assert actual == expected
    assert '\n\n' in actual


def test_unrecognized_adapter_is_rejected_without_writing(tmp_path):
    worker = tmp_path / 'hybrid_rollout/luban_direct/worker.py'
    worker.parent.mkdir(parents=True)
    worker.write_text('unexpected source')
    with pytest.raises(ValueError, match='Unknown local adapter'):
        align_published_policy(tmp_path, REFERENCE)
    assert worker.read_text() == 'unexpected source'

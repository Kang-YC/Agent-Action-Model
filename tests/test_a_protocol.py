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


def test_image_activity_cannot_extend_physical_progress_deadline(tmp_path):
    from agent_action.a_protocol import guard_development_progress
    path = tmp_path / RUN_PATH
    path.parent.mkdir(parents=True)
    path.write_text('''def run(rollout):
        deadline = 10000
        # stalled_turns = 0 if turn_control_progress else stalled_turns + 1
        while True:
            remaining = deadline - time.monotonic()
            time.now += 1
            deadline = time.now + 10000
''')
    clock = SimpleNamespace(now=0)
    clock.monotonic = lambda: clock.now
    guard_development_progress(tmp_path, timeout_seconds=3)
    scope = dict(time=clock)
    exec(compile(path.read_text(), str(path), 'exec'), scope)
    with pytest.raises(RuntimeError, match='No physical control progress'):
        scope['run'](SimpleNamespace(tick=0))
    assert clock.now == 3


@pytest.mark.parametrize('published', [False, True])
def test_translation_wording_is_shared_by_prompt_tool_and_receipt(tmp_path, published):
    from agent_action.a_protocol import unify_translation_guidance
    from agent_action.robot import CONTRACT
    skill = tmp_path / 'hybrid_rollout/robodojo/skill'
    (skill / 'context').mkdir(parents=True)
    direct_skill = tmp_path / 'hybrid_rollout/robodojo/robodojo-gpt-only-rollout'
    shutil.copytree(REFERENCE / 'hybrid_rollout/robodojo/robodojo-gpt-only-rollout', direct_skill)
    for name in ('SKILL.md', 'context/eef_control.md', 'run.py'):
        shutil.copy2(REFERENCE / 'hybrid_rollout/robodojo/skill' / name, skill / name)
    if published:
        (skill / 'run.py').write_bytes(subprocess.check_output(
            ['git', '-C', str(REFERENCE), 'show', f'{REFERENCE_COMMIT}:{RUN_PATH}']))
    before = ast.parse((skill / 'run.py').read_text())
    metadata = unify_translation_guidance(tmp_path)
    rule = CONTRACT.translation_rule()
    assert metadata['changes_acceptance_rule'] is False
    assert rule in (direct_skill / 'SKILL.md').read_text()
    assert rule in (direct_skill / 'context/eef_control.md').read_text()
    after = ast.parse((skill / 'run.py').read_text())
    funcs = [node for node in after.body if isinstance(node, ast.FunctionDef)
             and node.name in ('tool_specs', 'rejected_input')]
    scope = dict(CONTROLLER_VERSION='test', direct_response_schema=lambda: {}, _obj=lambda value: value)
    exec(compile(ast.Module(body=funcs, type_ignores=[]), '<guidance>', 'exec'), scope)
    act = next(t for t in scope['tool_specs']('gpt_only') if t['name'] == 'robodojo_act')
    assert rule in act['description']
    rollout = SimpleNamespace(tick=0, next_call=lambda: {'tool': 'robodojo_act'})
    receipt = scope['rejected_input'](ValueError('Recovery EEF target exceeds 5 cm'), rollout, {}, 1)
    assert receipt['translation_constraint'] == rule
    assert receipt['no_execution'] is True
    unchanged = lambda tree: [ast.dump(n) for n in tree.body if not (
        isinstance(n, ast.FunctionDef) and n.name in ('tool_specs', 'rejected_input'))]
    assert unchanged(before) == unchanged(after)


def test_numeric_feedback_measures_both_errors_without_mutation():
    from copy import deepcopy
    from agent_action.a_protocol import eef_numeric_feedback
    request = {'request_id': 'r', 'current_eef': {arm: {'position': [0, 0, 0]} for arm in ('left', 'right')}}
    args = {'response': {'mode': 'eef', 'request_id': 'r', 'target': {
        'left': {'position': [.03, .04, 0], 'quaternion_wxyz': [1, 0, 0, 0]},
        'right': {'position': [.05, .05, .05], 'quaternion_wxyz': [.707, 0, 0, .707]}}}}
    original = deepcopy((args, request))
    result = eef_numeric_feedback(args, request)['arms']
    assert result['left']['distance_m'] == pytest.approx(.05)
    assert result['left']['translation_exceeded'] is False
    assert result['right']['distance_m'] == pytest.approx(.086602540378)
    assert result['right']['translation_exceeded'] is True
    assert result['right']['quaternion_norm_invalid'] is True
    assert (args, request) == original
    args['response']['request_id'] = 'stale'
    assert 'unavailable' in eef_numeric_feedback(args, request)
    assert eef_numeric_feedback(None, request) == {}


@pytest.mark.parametrize('published', [False, True])
def test_numeric_receipt_snapshot_executes_without_harness_imports(tmp_path, published):
    import math
    from agent_action.a_protocol import add_numeric_rejection_feedback
    path = tmp_path / RUN_PATH
    path.parent.mkdir(parents=True)
    source = (subprocess.check_output(['git', '-C', str(REFERENCE), 'show', f'{REFERENCE_COMMIT}:{RUN_PATH}'], text=True)
              if published else (REFERENCE / RUN_PATH).read_text())
    path.write_text(source)
    metadata = add_numeric_rejection_feedback(tmp_path)
    tree = ast.parse(path.read_text())
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('eef_numeric_feedback', 'rejected_input')]
    scope = dict(CONTROLLER_VERSION='test', math=math)
    exec(compile(ast.Module(body=funcs, type_ignores=[]), '<receipt>', 'exec'), scope)
    request = {'request_id': 'r', 'current_eef': {'left': {'position': [0, 0, 0]}}}
    rollout = SimpleNamespace(request=request, phase='act', tick=0, next_call=lambda: {})
    args = {'response': {'request_id': 'r', 'mode': 'eef', 'target': {'left': {'position': [.06, 0, 0], 'quaternion_wxyz': [1, 0, 0, 0]}}}}
    packet = scope['rejected_input'](ValueError('Recovery EEF target exceeds 5 cm'), rollout, args, 1)
    assert packet['no_execution'] is True
    assert packet['eef_numeric_feedback']['arms']['left']['distance_m'] == .06
    assert metadata['changes_acceptance_rule'] is False
    unchanged = lambda t: [ast.dump(n) for n in t.body if not (isinstance(n, ast.FunctionDef) and n.name in ('eef_numeric_feedback', 'rejected_input'))]
    assert unchanged(ast.parse(source)) == unchanged(tree)


def test_translation_guidance_reaches_actual_direct_prompt(tmp_path):
    from agent_action.a_protocol import unify_translation_guidance
    from agent_action.robot import CONTRACT
    worker = tmp_path / 'hybrid_rollout/luban_direct/worker.py'
    worker.parent.mkdir(parents=True)
    shutil.copy2(REFERENCE / 'hybrid_rollout/luban_direct/worker.py', worker)
    for name in ('skill', 'robodojo-gpt-only-rollout'):
        shutil.copytree(REFERENCE / 'hybrid_rollout/robodojo' / name,
                        tmp_path / 'hybrid_rollout/robodojo' / name)
    align_published_policy(tmp_path, REFERENCE)
    metadata = unify_translation_guidance(tmp_path)
    # Resolve the root from the actual worker expression, rather than assume the
    # shared implementation's skill/ directory also supplies Direct's prompt.
    tree = ast.parse(worker.read_text())
    root_expr = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'root' for t in n.targets))
    root = eval(compile(ast.Expression(root_expr), '<root>', 'eval'),
                dict(Path=Path, __file__=str(worker)))
    prompt = eval(compile(ast.Expression(prompt_expression(worker.read_text())), '<prompt>', 'eval'),
                  dict(root=root, teacher=root/'context/teacher_context.md',
                       self=SimpleNamespace(agent_workspace=Path('/episode/agent'))))
    assert CONTRACT.translation_rule() in prompt
    assert CONTRACT.translation_rule() in (root/'context/eef_control.md').read_text()
    assert metadata['version'] == 'euclidean_translation_guidance_v2'


@pytest.mark.parametrize('published', [False, True])
@pytest.mark.parametrize('numeric', [False, True])
def test_response_type_feedback_preserves_validation_and_other_receipts(tmp_path, published, numeric):
    from copy import deepcopy
    from agent_action.a_protocol import (clarify_response_rejection,
        add_numeric_rejection_feedback, unify_translation_guidance)

    for name in ('skill', 'robodojo-gpt-only-rollout'):
        shutil.copytree(REFERENCE / 'hybrid_rollout/robodojo' / name,
                        tmp_path / 'hybrid_rollout/robodojo' / name)
    path = tmp_path / RUN_PATH
    if published:
        path.write_bytes(subprocess.check_output(
            ['git', '-C', str(REFERENCE), 'show', f'{REFERENCE_COMMIT}:{RUN_PATH}']))
    unify_translation_guidance(tmp_path)
    if numeric:
        add_numeric_rejection_feedback(tmp_path)
    before = ast.parse(path.read_text())
    metadata = clarify_response_rejection(tmp_path)
    after = ast.parse(path.read_text())
    names = ('rejected_input', 'response_input_feedback', 'eef_numeric_feedback')
    funcs = [n for n in after.body if isinstance(n, ast.FunctionDef) and n.name in names]
    scope = dict(CONTROLLER_VERSION='test')
    exec(compile(ast.Module(body=funcs, type_ignores=[]), '<receipt>', 'exec'), scope)
    rollout = SimpleNamespace(request={'request_id': 'current', 'current_eef': {}},
                              phase='act', tick=6, next_call=lambda: {'tool': 'robodojo_act'})
    native_error = ValueError('Response must match the current observation request_id')
    # Includes the observed malformed JSON string with a correct embedded ID.
    for response in ('{"request_id":"current"}}', [], None, True, 1):
        args = {'response': response}
        original = deepcopy(args)
        packet = scope['rejected_input'](native_error, rollout, args, 1)
        assert packet['input_error'] == 'response_type'
        assert packet['native_error'] == str(native_error)
        assert 'JSON object' in packet['error']
        assert packet['no_execution'] is True and packet['step_id'] == 6
        assert args == original
    packet = scope['rejected_input'](native_error, rollout, {'response': {'request_id': 'stale'}}, 2)
    assert packet['input_error'] == 'request_id_mismatch'
    assert packet['error'] == str(native_error)
    packet = scope['rejected_input'](ValueError('different rejection'), rollout, {}, 3)
    assert packet['error'] == 'different rejection' and 'input_error' not in packet
    assert metadata['changes_acceptance_rule'] is False
    unchanged = lambda tree: [ast.dump(n) for n in tree.body if not (
        isinstance(n, ast.FunctionDef) and n.name in ('rejected_input', 'response_input_feedback'))]
    assert unchanged(before) == unchanged(after)
    saved = path.read_text()
    with pytest.raises(ValueError):
        clarify_response_rejection(tmp_path)
    assert path.read_text() == saved

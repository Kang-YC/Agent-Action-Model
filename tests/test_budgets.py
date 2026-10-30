import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from agent_action.a_line import published_case_plan, validate_native_budget, validate_development_budget
from agent_action.direct import episode_wait_timeout, nonnegative_int, simulator_error, startup_timeout, task_outcome, wait_for_controller


def test_controller_wait_detects_service_exit_without_wall_cap():
    from unittest.mock import Mock

    worker = Mock(args=["controller"])
    worker.poll.return_value = None
    service = Mock()
    service.poll.return_value = 0
    with pytest.raises(RuntimeError, match="Simulator exited 0"):
        wait_for_controller(worker, {"Simulator": service}, None)
    worker.poll.return_value = 7
    assert wait_for_controller(worker, {"Simulator": service}, None) == 7
    worker.poll.return_value = None
    service.poll.return_value = None
    with pytest.raises(subprocess.TimeoutExpired):
        wait_for_controller(worker, {"Simulator": service}, 0)


def test_zero_wall_cap_keeps_startup_deadline_and_allows_episode_completion():
    assert startup_timeout(0) == 300
    assert startup_timeout(60) == 60
    assert episode_wait_timeout(0, elapsed=50000) is None
    assert episode_wait_timeout(60, elapsed=15) == 45
    process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(7)"])
    assert process.wait(timeout=episode_wait_timeout(0, elapsed=50000)) == 7
    with pytest.raises(argparse.ArgumentTypeError, match="non-negative"):
        nonnegative_int("-1")


def test_stack_bowls_uses_400_step_development_cap_without_changing_native_horizon():
    plan = json.loads(Path("configs/a_stack_bowls_development.json").read_text())
    assert plan['native_control_horizon'] == 800
    assert plan['max_control_steps'] == 400
    validate_development_budget(plan)
    with pytest.raises(ValueError):
        validate_native_budget(plan)
    for limit in (0, 801):
        invalid = copy.deepcopy(plan)
        invalid['max_control_steps'] = limit
        with pytest.raises(ValueError):
            validate_development_budget(invalid)
    for key in ('max_decisions', 'max_total_tokens', 'wall_seconds'):
        invalid = copy.deepcopy(plan)
        invalid[key] = 1
        with pytest.raises(ValueError):
            validate_development_budget(invalid)


def test_all_published_cases_use_their_own_native_horizons_and_variants():
    panel = json.loads(Path("configs/a_published_ten_task_panel.json").read_text())
    expected = {"arrange_largest_number": 1050, "build_tower": 1050, "classify_objects": 1100,
                "classify_objects_by_language": 1100, "fold_clothes": 500, "imitate_sorting_sequence": 1600,
                "make_kong": 600, "organize_table": 1000, "pack_objects_into_box": 1300,
                "put_bottles_into_dustbin": 700}
    assert len(panel["cases"]) == 50
    for case in panel["cases"]:
        plan = published_case_plan(panel, case["case_id"])
        validate_native_budget(plan)
        assert plan["max_control_steps"] == expected[case["task"]]
        assert plan["task"] == case["task"] + ("_random" if case["variant"] == "random" else "")
        assert plan["layout_id"] == case["seeds"]["layout_id"]
    with pytest.raises(ValueError, match="Expected one published case"):
        published_case_plan(panel, "unknown")
    altered = copy.deepcopy(panel)
    altered["cases"][0]["native_horizon"] = 1
    with pytest.raises(ValueError, match="hash mismatch"):
        published_case_plan(altered, altered["cases"][0]["case_id"])


@pytest.mark.parametrize(("steps", "success", "expected"), [
    (799, False, "incomplete"), (800, False, "failure_control_step_limit"),
    (801, False, "failure_control_step_limit"), (800, True, "success"),
])
def test_native_step_limit_failure_boundary(steps, success, expected):
    assert task_outcome(dict(step_id=steps, success=success), {}, 800) == expected


def test_simulator_faults_and_early_budgets_are_not_step_limit_failures():
    assert simulator_error("PxgCudaDeviceMemoryAllocator failed to allocate memory 100000000 bytes! Result = 2") == "gpu_memory_allocation"
    assert simulator_error("Scene state is corrupted. Simulation cannot continue!") == "scene_state_corrupted"
    assert task_outcome(dict(step_id=147, reason="controller_error"), {}, 800) == "incomplete"
    assert task_outcome(dict(step_id=1, reason="control_step_budget"), dict(native_step_limit=800), 1) == "budget_censored"
    assert task_outcome(dict(step_id=800, success=False), dict(status="invalid_native_layout"), 800) == "invalid_native_layout"


def test_400_step_development_stop_is_censored_not_native_failure():
    result = dict(step_id=400, reason='control_step_budget', success=False)
    native = dict(complete=False, native_control_steps=400, native_step_limit=800)
    assert task_outcome(result, native, 400) == 'budget_censored'


def test_documented_finish_allows_simulator_to_exit_before_worker(tmp_path):
    from unittest.mock import Mock
    marker = tmp_path / 'termination.json'
    marker.write_text('{"reason":"operator_interrupt"}')
    worker = Mock()
    worker.poll.return_value = None
    worker.wait.return_value = 1
    sim = Mock()
    sim.poll.return_value = 0
    assert wait_for_controller(worker, {'Simulator': sim}, None, marker) == 1
    worker.wait.assert_called_once_with(timeout=30)
    sim.poll.return_value = 2
    with pytest.raises(RuntimeError):
        wait_for_controller(worker, {'Simulator': sim}, None, marker)


def test_controller_image_limit_remains_primary_cause_after_clean_simulator_exit():
    from agent_action.direct import apply_controller_termination
    native = dict(complete=False, native_score=None, native_success=None)
    summary = dict(status='infrastructure_error',
                   error='Simulator exited 0 while controller was running; inspect logs', native_outcome=native)
    termination = dict(reason='controller_error', error='BadRequestError: At most 12 image(s) may be provided in one prompt.')
    apply_controller_termination(summary, termination)
    assert summary['status'] == 'controller_error'
    assert summary['failure_category'] == 'model_image_limit'
    assert summary['task_outcome'] == 'incomplete'
    assert summary['native_outcome'] == native
    assert summary['controller_termination'] == termination
    assert summary['error'].startswith('Simulator exited 0')


def test_controller_cleanup_cannot_mask_a_real_simulator_fault():
    from agent_action.direct import apply_controller_termination
    summary = dict(status='simulator_error', failure_category='gpu_memory_allocation')
    apply_controller_termination(summary, dict(reason='operator_interrupt'))
    assert summary['status'] == 'simulator_error'
    assert summary['failure_category'] == 'gpu_memory_allocation'
    summary = dict(status='infrastructure_error', error='Simulator exited 0 while controller was running; inspect logs')
    apply_controller_termination(summary, dict(reason='operator_interrupt'))
    assert summary['status'] == 'operator_interrupted'


@pytest.mark.parametrize('steps,probe', [(0, False), (700, False), (30, True), (800, True)])
def test_frozen_layout_control_cap_is_not_formal_evaluation(steps, probe):
    from types import SimpleNamespace
    from agent_action.direct import has_probe_budget

    panel = json.loads(Path('configs/a_published_ten_task_panel.json').read_text())
    args = SimpleNamespace(task='put_bottles_into_dustbin', max_control_steps=steps,
                           max_decisions=0, max_total_tokens=0, wall_seconds=0)
    assert has_probe_budget(args, panel) is probe
    args.max_total_tokens = 250000
    assert has_probe_budget(args, panel) is True

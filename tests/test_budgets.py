import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from agent_action.a_line import published_case_plan, validate_native_budget
from agent_action.direct import episode_wait_timeout, nonnegative_int, startup_timeout


def test_zero_wall_cap_keeps_startup_deadline_and_allows_episode_completion():
    assert startup_timeout(0) == 300
    assert startup_timeout(60) == 60
    assert episode_wait_timeout(0, elapsed=50000) is None
    assert episode_wait_timeout(60, elapsed=15) == 45
    process = subprocess.Popen([sys.executable, "-c", "raise SystemExit(7)"])
    assert process.wait(timeout=episode_wait_timeout(0, elapsed=50000)) == 7
    with pytest.raises(argparse.ArgumentTypeError, match="non-negative"):
        nonnegative_int("-1")


def test_stack_bowls_uses_native_horizon_without_extra_caps():
    plan = json.loads(Path("configs/a_stack_bowls_development.json").read_text())
    assert plan["native_control_horizon"] == plan["max_control_steps"] == 800
    validate_native_budget(plan)
    for key in ("max_decisions", "max_total_tokens", "wall_seconds", "max_control_steps"):
        invalid = copy.deepcopy(plan)
        invalid[key] = 1
        with pytest.raises(ValueError):
            validate_native_budget(invalid)


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

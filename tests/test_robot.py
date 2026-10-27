from copy import deepcopy
import math

import pytest

from agent_action.robot import CONTRACT


def poses():
    return {arm: dict(position=[0., 0., 0.], quaternion_wxyz=[1., 0., 0., 0.], gripper_closed=False)
            for arm in ("left", "right")}


@pytest.mark.parametrize(("field", "value"), [
    ("position", [0, 0, .050001]), ("position", [0, float("nan"), 0]),
    ("position", [0, 0]), ("quaternion_wxyz", [2, 0, 0, 0]),
    ("quaternion_wxyz", [math.cos(.176), math.sin(.176), 0, 0]),
    ("gripper_closed", 1),
])
def test_rejects_invalid_targets_on_either_arm(field, value):
    for arm in ("left", "right"):
        current = poses()
        target = deepcopy(current)
        target[arm][field] = value
        with pytest.raises(ValueError):
            CONTRACT.validate(**target, steps=5, current=current)


@pytest.mark.parametrize("steps", [0, 6, True, 1.0])
def test_rejects_invalid_steps(steps):
    with pytest.raises(ValueError):
        CONTRACT.validate(**poses(), steps=steps, current=poses())


def test_boundary_and_quaternion_sign_equivalence():
    current = poses()
    target = deepcopy(current)
    target["left"]["position"][0] = .05
    target["left"]["quaternion_wxyz"] = [math.cos(.175), math.sin(.175), 0, 0]
    target["right"]["quaternion_wxyz"] = [-1, 0, 0, 0]
    assert CONTRACT.validate(**target, steps=5, current=current) == target

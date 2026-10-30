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


@pytest.mark.parametrize('steps', [1, 5])
@pytest.mark.parametrize('arm', ['left', 'right'])
def test_translation_is_per_arm_euclidean_not_per_axis(steps, arm):
    current = poses()
    target = deepcopy(current)
    target[arm]['position'] = [.03, .04, 0]
    assert CONTRACT.validate(**target, steps=steps, current=current) == target
    for position in ([.05, .05, .05], [.04, .02, -.03]):
        target[arm]['position'] = position
        with pytest.raises(ValueError, match='translation bound'):
            CONTRACT.validate(**target, steps=steps, current=current)
    target = deepcopy(current)
    target['left']['position'] = [.05, 0, 0]
    target['right']['position'] = [0, .05, 0]
    assert CONTRACT.validate(**target, steps=steps, current=current) == target

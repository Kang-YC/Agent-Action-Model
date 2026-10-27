"""Deterministic protocol peer checks; these do not simulate physics."""

from copy import deepcopy
import json

import numpy as np
import pytest

from agent_action.native import NativeRobot
from agent_action.robot import CONTRACT


class ProtocolPeer:
    def __init__(self, fail_step=False):
        self.calls = []
        self.tick = 0
        self.fail_step = fail_step
        self.closed = False

    def request(self, op, **kwargs):
        self.calls.append((op, deepcopy(kwargs)))
        if op == "metadata":
            return dict(robot_adapter="dual_arx_x5", frame="environment_origin", eef_link="link6",
                        control_dt=.04, cameras=list(CONTRACT.cameras), action_dim=14,
                        gripper_semantics="continuous_0_closed_1_open", task="test")
        if op == "reset":
            return dict(episode_id="episode", step_id=0)
        assert kwargs["step_id"] == self.tick
        assert kwargs["episode_id"] == "episode"
        if op == "switch_control_source":
            return dict(physical_steps=0)
        if op == "teacher_observation":
            return dict(**{camera: np.zeros((4, 4, 3), np.uint8) for camera in CONTRACT.cameras},
                        eef_positions=np.zeros((2, 3)), eef_quaternions_wxyz=np.array([[1., 0, 0, 0]]*2),
                        states=np.zeros(14), instruction="test", remaining_steps=100-self.tick)
        if op == "eef_joint_target":
            return dict(action=[0.]*14, diagnostics={})
        if op == "chunk_step":
            self.tick += 1
            if self.fail_step:
                raise TimeoutError("ACK lost after execution")
            return dict(episode_id="episode", step_id=self.tick, steps=[dict(
                valid=True, terminated=False, truncated=False, success=False)])
        if op == "finish_pilot":
            return dict(step_id=self.tick)
        raise AssertionError(op)

    def close(self):
        self.closed = True


def test_stepwise_ack_cell_limit_and_observation(tmp_path):
    peer = ProtocolPeer()
    robot = NativeRobot(peer, tmp_path / "run", "test")
    targets = deepcopy(robot.current)
    for target in targets.values():
        target["gripper_closed"] = False
    result = robot.move_to(**targets, steps=3)
    assert [op for op, _ in peer.calls[4:]] == ["eef_joint_target", "chunk_step"]*3 + ["teacher_observation"]
    assert result["step_id"] == 3 and len(result["images"]) == 3
    assert not result["current_eef"]["left"]["gripper_closed"]
    assert result["native_gripper_opening_feedback"] == [0., 0.]
    assert "success" not in result
    before = len(peer.calls)
    with pytest.raises(RuntimeError, match="one move_to"):
        robot.move_to(**robot.current)
    assert len(peer.calls) == before
    robot.begin_cell()
    robot.move_to(**robot.current, steps=1)
    robot.close()
    assert peer.closed
    assert json.loads((robot.output / "action_0001.json").read_text())["end_step"] == 3


def test_lost_ack_is_not_retried_or_finished(tmp_path):
    peer = ProtocolPeer(fail_step=True)
    robot = NativeRobot(peer, tmp_path / "run", "test")
    with pytest.raises(TimeoutError):
        robot.move_to(**robot.current)
    before = len(peer.calls)
    robot.begin_cell()
    with pytest.raises(RuntimeError, match="uncertain"):
        robot.move_to(**robot.current)
    robot.close()
    assert len(peer.calls) == before and peer.tick == 1 and peer.closed
    assert json.loads((robot.output / "uncertain.json").read_text())["automatic_retry"] is False


def test_invalid_target_never_reaches_native_rpc(tmp_path):
    peer = ProtocolPeer()
    robot = NativeRobot(peer, tmp_path / "run", "test")
    target = deepcopy(robot.current)
    target["right"]["position"][2] = .06
    before = len(peer.calls)
    with pytest.raises(ValueError):
        robot.move_to(**target)
    assert len(peer.calls) == before and peer.tick == 0
    robot.close()


class ProtocolContext:
    def __init__(self, *, output, requirements=(), allowed_tools=()):
        self.robot = NativeRobot(ProtocolPeer(), output, "test")
        self.session_globals = {"Observation": self.robot.packet, "_begin_robot_cell": self.robot.begin_cell}

    def close(self):
        self.robot.close()


def test_persistent_python_environment_enforces_cell_limit_and_emits_images(tmp_path):
    from agent_action.toolset import RobotEnvironment

    with RobotEnvironment(toolset="agent_action.toolset:build_registry",
                          context_factory="tests.test_native:ProtocolContext",
                          context_kwargs={"output": str(tmp_path / "run")}, memory_limit_gb=0) as environment:
        action = "move_to(Observation['current_eef']['left'], Observation['current_eef']['right'], steps=1)"
        first = environment.execute({"code": action + "\n" + action})
        assert first["returncode"] == 1 and "one move_to" in first["output"]
        assert first["output"].count("<MSWEA_IMAGE_PATH>") == 3
        assert len(first["extra"]["artifacts"]) == 3
        assert all(item["mime_type"] == "image/png" for item in first["extra"]["artifacts"])
        second = environment.execute({"code": action + "\nprint(Observation['step_id'])"})
        assert second["returncode"] == 0 and second["output"].splitlines()[-1] == "2"

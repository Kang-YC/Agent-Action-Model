"""B-line image history and native-terminal guards."""

import json

import pytest
from PIL import Image

from agent_action.b_model import BasePythonModel
from agent_action.b_run import RobotAgent
from minisweagent.exceptions import LimitsExceeded


def test_h0_sends_only_latest_images_without_mutating_history(tmp_path):
    paths = []
    for i in range(6):
        path = tmp_path / f"{i}.png"
        Image.new("RGB", (4, 4), (i, 0, 0)).save(path)
        paths.append(path)
    messages = [
        dict(
            role="user",
            content=[
                dict(type="text", text=f"state {i}"),
                *[
                    dict(type="image_path", image_path=dict(path=str(p)))
                    for p in paths[i * 3 : i * 3 + 3]
                ],
            ],
        )
        for i in range(2)
    ]
    from minisweagent.models.litellm_python_model import LitellmPythonModelConfig

    model = object.__new__(BasePythonModel)
    model.config = LitellmPythonModelConfig(model_name="openai/test")
    actual = model._prepare_messages_for_api(messages)
    assert len(actual[0]["content"]) == 1
    assert len(actual[1]["content"]) == 4
    assert all(x["type"] == "image_url" for x in actual[1]["content"][1:])
    assert len(messages[0]["content"]) == 4


def test_native_terminal_stops_before_another_model_request(tmp_path):
    packet = tmp_path / "observation_0001"
    packet.mkdir()
    (packet / "observation.json").write_text(
        json.dumps(dict(rollout_finished=True, step_id=1))
    )
    agent = object.__new__(RobotAgent)
    agent.robot_output = tmp_path
    agent.control_limit = 10
    agent.token_limit = 0
    with pytest.raises(LimitsExceeded) as caught:
        agent.query()
    assert caught.value.messages[0]["extra"]["exit_status"] == "native_terminal"


@pytest.mark.parametrize(
    "step, tokens, expected", [(10, 0, "control_budget"), (1, 100, "token_budget")]
)
def test_budgets_stop_before_model_request(tmp_path, step, tokens, expected):
    packet = tmp_path / "observation_0001"
    packet.mkdir()
    (packet / "observation.json").write_text(
        json.dumps(dict(rollout_finished=False, step_id=step))
    )
    agent = object.__new__(RobotAgent)
    agent.robot_output = tmp_path
    agent.control_limit = 10
    agent.token_limit = 50
    agent.tokens = lambda: tokens
    with pytest.raises(LimitsExceeded) as caught:
        agent.query()
    assert caught.value.messages[0]["extra"]["exit_status"] == expected


@pytest.mark.parametrize(
    "valid, complete, status, expected",
    [
        (False, False, "control_budget", "budget_censored"),
        (False, False, "Submitted", "model_stopped"),
        (True, True, "native_terminal", "native_completed"),
        (False, True, "native_terminal", "infrastructure_error"),
    ],
)
def test_summary_uses_only_eligible_native_labels(
    tmp_path, valid, complete, status, expected
):
    from agent_action.b_report import summarize

    sim = tmp_path / "sim"
    sim.mkdir()
    (sim / "evaluation_outcome.json").write_text(
        json.dumps(
            dict(
                complete=complete,
                valid_for_success_rate=valid,
                native_success=False,
                native_score=0.25,
            )
        )
    )
    (tmp_path / "request_0001.input.json.gz").touch()
    (tmp_path / "request_0002.input.json.gz").touch()
    (tmp_path / "requests.jsonl").write_text(
        json.dumps(
            dict(status="completed", usage=dict(total_tokens=20), latency_seconds=1)
        )
        + "\n"
    )
    report = summarize(tmp_path, status=status, sim_output=sim)
    assert report["classification"] == expected
    assert report["requests_without_usage"] == 1
    assert report["scored"] == (valid and complete)
    assert report["native_success"] is (False if valid and complete else None)
    assert report["native_score"] == (0.25 if valid and complete else None)


def test_uncertainty_wins_over_budget_and_terminal(tmp_path):
    packet = tmp_path / "observation_0001"
    packet.mkdir()
    (packet / "observation.json").write_text(
        json.dumps(dict(rollout_finished=True, step_id=10))
    )
    (tmp_path / "uncertain.json").write_text("{}")
    agent = object.__new__(RobotAgent)
    agent.robot_output = tmp_path
    agent.control_limit = 10
    agent.token_limit = 0
    with pytest.raises(LimitsExceeded) as caught:
        agent.query()
    assert caught.value.messages[0]["extra"]["exit_status"] == "uncertain_execution"


def test_robot_kernel_timeout_never_restarts_session(tmp_path):
    from agent_action.toolset import RobotEnvironment

    with RobotEnvironment(
        toolset="agent_action.toolset:build_registry",
        context_factory="tests.test_native:ProtocolContext",
        context_kwargs=dict(output=str(tmp_path / "robot")),
        memory_limit_gb=0,
        timeout=0.1,
    ) as env:
        with pytest.raises(RuntimeError, match="no retry"):
            env.execute(dict(code="import time; time.sleep(2)"))
        with pytest.raises(RuntimeError, match="refusing session restart"):
            env.execute(dict(code='print("must not execute")'))

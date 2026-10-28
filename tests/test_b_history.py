import copy
import io
import json
import urllib.error
from types import SimpleNamespace

import pytest

from agent_action.b_history import select_history
from agent_action.b_model import BasePythonModel, ContextLimitExceeded
from agent_action.b_report import summarize


def history():
    messages = [dict(role="system", content="robot rules"), dict(role="user", content="task")]
    for i in range(6):
        messages.append(dict(role="assistant", tool_calls=[dict(id=str(i))]))
        messages.append(dict(role="tool", tool_call_id=str(i), content=(
            [dict(type="text", text="measured state"),
             dict(type="image_path", image_path=dict(path="latest.png"))]
            if i == 1 else f"result {i}")))
    return messages


def test_window_retains_complete_calls_latest_observation_and_initial_instruction():
    messages = history()
    before = copy.deepcopy(messages)
    selected, audit = select_history(messages, 2)
    # Keep initial instruction, observation-producing turn 1, and recent turns 4,5.
    assert audit["retained_message_indices"] == [0, 1, 4, 5, 10, 11, 12, 13]
    assert [m["tool_call_id"] for m in selected if m["role"] == "tool"] == ["1", "4", "5"]
    for i, m in enumerate(selected):
        if m["role"] == "tool":
            assert selected[i - 1]["tool_calls"][0]["id"] == m["tool_call_id"]
    assert "6 earlier messages" in selected[0]["content"]
    assert "Python variables persist unchanged" in selected[0]["content"]
    assert all(len(m["sha256"]) == 64 for m in audit["omitted_messages"])
    assert messages == before


def test_default_keeps_all_text_and_no_notice_before_window_boundary():
    messages = history()
    for turns in (0, 6, 8):
        selected, audit = select_history(messages, turns)
        assert selected == messages
        assert not audit["omitted_messages"]
    with pytest.raises(ValueError):
        select_history(messages, -1)


@pytest.mark.parametrize("context_error", [True, False])
def test_context_rejection_classified_without_retry(tmp_path, context_error):
    detail = {"error": {"message": "This model's maximum context length is 32768 tokens."
                       if context_error else "Invalid tool schema"}}
    calls = []
    def chat(*args, **kwargs):
        calls.append(1)
        raise urllib.error.HTTPError("local", 400, "Bad Request", {},
                                     io.BytesIO(json.dumps(detail).encode()))
    model = object.__new__(BasePythonModel)
    model.client = SimpleNamespace(chat=chat, config={})
    model.output, model.index = tmp_path, 0
    model.history_selection = dict(policy="all_text")
    with pytest.raises(ContextLimitExceeded if context_error else urllib.error.HTTPError):
        model._query([])
    assert calls == [1]
    assert json.loads((tmp_path / "request_0001.error.json").read_text())["detail"] == json.dumps(detail)
    assert len((tmp_path / "requests.jsonl").read_text().splitlines()) == 1


def test_context_exhaustion_is_unscored_and_distinct_from_simulator_error(tmp_path):
    summary = summarize(tmp_path, status="context_limit")
    assert summary["classification"] == "context_exhausted"
    assert not summary["scored"]
    assert summary["native_success"] is summary["native_score"] is None


def test_model_interrupt_is_not_retried():
    model = object.__new__(BasePythonModel)
    model._prepare_messages_for_api = lambda messages: messages
    calls = []

    def interrupt(*args, **kwargs):
        calls.append(1)
        raise KeyboardInterrupt()

    model._query = interrupt
    with pytest.raises(KeyboardInterrupt):
        model.query([])
    assert calls == [1]

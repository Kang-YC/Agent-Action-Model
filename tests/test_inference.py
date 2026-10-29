import base64
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_action.serve import checkpoint_manifest, server_arguments
from agent_action.bridge import image_manifest, prepare_request


def config():
    return json.loads(Path("configs/base_model.json").read_text())


def test_request_preserves_images_tool_receipts_and_serving_parameters():
    cfg = config()
    image = "data:image/png;base64," + base64.b64encode(b"image-content").decode()
    body = dict(model=cfg["served_model_name"], instructions="first", max_output_tokens=8192,
                input=[dict(role="developer", content="second"),
                       dict(role="user", content=[dict(type="input_image", image_url=image)]),
                       dict(type="function_call", name="step", call_id="call1", arguments='{"x":1}'),
                       dict(type="function_call_output", call_id="call1", output=[
                           dict(type="input_text", text="receipt"), dict(type="input_image", image_url=image)])],
                tools=[dict(type="function", name="step", parameters=dict(type="object", properties={}))])
    before = copy.deepcopy(body)
    request, mapping = prepare_request(body, cfg, {})
    assert body == before
    assert request["messages"][0] == dict(role="system", content="first\n\nsecond")
    assert request["messages"][2]["tool_calls"][0]["id"] == "call1"
    assert request["messages"][3] == dict(role="tool", tool_call_id="call1", content="receipt")
    assert len(image_manifest(request["messages"])) == 2
    assert request["max_completion_tokens"] == cfg["max_completion_tokens"]
    assert request["chat_template_kwargs"] == {"enable_thinking": False}
    assert request["temperature"] == 0 and mapping["step"]["name"] == "step"
    with pytest.raises(ValueError, match="differs"):
        prepare_request({**body, "model": "other-model"}, cfg, {})


def test_checkpoint_manifest_requires_every_indexed_shard(tmp_path):
    cfg = config()
    cfg["checkpoint"] = str(tmp_path)
    names = ["config.json", "generation_config.json", "chat_template.jinja", "processor_config.json",
             "tokenizer_config.json", "tokenizer.json"]
    for name in names:
        (tmp_path / name).write_text('{"architectures":["test"],"model_type":"test"}')
    (tmp_path / "model.safetensors.index.json").write_text(json.dumps(dict(weight_map={"a": "weights.safetensors"})))
    with pytest.raises(FileNotFoundError):
        checkpoint_manifest(cfg)
    (tmp_path / "weights.safetensors").write_bytes(b"weights")
    manifest = checkpoint_manifest(cfg)
    assert manifest["weight_bytes"] == 7 and len(manifest["files_sha256"]) == 7
    assert "not_hashed" in manifest["weight_identity_scope"]
    assert cfg["checkpoint"] in server_arguments(cfg)


def test_terminal_guard_delivers_final_receipt_before_stopping():
    from agent_action.direct_worker import RolloutFinished, StopAfterFinish

    receipts = []
    transport = SimpleNamespace(reply=lambda identifier, result: receipts.append((identifier, result)),
                                marker="forwarded")
    rollout = SimpleNamespace(phase="act")
    guarded = StopAfterFinish(transport, rollout)
    guarded.reply(1, {"step": 3})
    assert guarded.marker == "forwarded" and receipts == [(1, {"step": 3})]
    rollout.phase = "done"
    with pytest.raises(RolloutFinished):
        guarded.reply(2, {"step": 6, "finished": True})
    assert receipts[-1] == (2, {"step": 6, "finished": True})


def test_assistant_text_and_call_share_one_chat_message():
    cfg = config()
    body = dict(model=cfg['served_model_name'], input=[
        dict(role='assistant', content='I will move.'),
        dict(type='function_call', name='step', call_id='c1', arguments='{"x":1}'),
        dict(type='function_call_output', call_id='c1', output='ack')],
        tools=[dict(type='function', name='step', parameters=dict(type='object'))])
    request, _ = prepare_request(body, cfg, {})
    assert len(request['messages']) == 2
    assert request['messages'][0]['content'] == 'I will move.'
    assert request['messages'][0]['tool_calls'][0]['id'] == 'c1'
    assert request['messages'][1]['tool_call_id'] == 'c1'

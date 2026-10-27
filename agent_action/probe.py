"""Real Codex/model probe: two dynamic-tool calls, three changing images each."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time

from PIL import Image

from hybrid_rollout.robodojo.skill.run import toml_value
from hybrid_rollout.robodojo.skill.transport import StdioAppServer


def codex_config(config: dict) -> dict:
    return dict(model=config["served_model_name"], model_provider="LocalBase", web_search="disabled",
                allow_login_shell=False, model_context_window=config["max_model_len"],
                model_auto_compact_token_limit=config["max_model_len"]*3//4,
                features={"multi_agent": False, "apps": False, "goals": False, "shell_snapshot": False,
                          "shell_tool": False, "view_image": False},
                analytics={"enabled": False},
                model_providers={"LocalBase": dict(name="LocalBase", wire_api="responses",
                    base_url=f"http://127.0.0.1:{config['bridge_port']}/v1", supports_websockets=False,
                    requires_openai_auth=False, request_max_retries=0, stream_max_retries=0,
                    stream_idle_timeout_ms=600000)})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/base_model.json"))
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    home = output / "codex_home"
    home.mkdir()
    os.environ["CODEX_HOME"] = str(home)
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY"):
        os.environ.pop(key, None)
    cfg = codex_config(config)
    argv = [str(args.codex), "app-server"]
    for key, value in cfg.items():
        argv += ["-c", key + "=" + toml_value(value)]
    colors = ["red", "green", "blue"]
    secrets.SystemRandom().shuffle(colors)
    second = colors[1:] + colors[:1]
    expected = [dict(round=index+1, colors=order, receipt=secrets.token_hex(8))
                for index, order in enumerate((colors, second))]
    rgb = {"red": (235, 25, 25), "green": (25, 190, 25), "blue": (25, 25, 235)}
    (output / "expected.json").write_text(json.dumps(expected, indent=2))
    (output / "launch.json").write_text(json.dumps(dict(config=cfg, argv=argv,
        codex_version=subprocess.check_output([str(args.codex), "--version"], text=True).strip(),
        codex_sha256=hashlib.sha256(args.codex.read_bytes()).hexdigest()), indent=2))
    transport = StdioAppServer(argv, output)
    calls, messages = [], []
    result = dict(passed=False, model=config["served_model_name"], tool_calls=calls)
    started = time.monotonic()
    try:
        transport.request("initialize", dict(clientInfo={"name": "base-inference-probe", "version": "1"},
            capabilities={"experimentalApi": True}), 30)
        transport.notify("initialized", {})
        tools = [dict(name="probe_observation", description="Return three camera color cards and a fresh receipt for this round.",
                      inputSchema=dict(type="object", properties={"round": {"type": "integer", "enum": [1, 2]}},
                                       required=["round"], additionalProperties=False))]
        prompt = ("Run a two-round multimodal protocol test. Call probe_observation with round=1, inspect all three "
                  "images in camera order 0,1,2 and remember their basic English colors and the receipt. "
                  "Then call probe_observation with round=2 and inspect the new three images. "
                  "Finally output only JSON: {\"rounds\":[{\"round\":1,\"colors\":[...],\"receipt\":\"...\"},"
                  "{\"round\":2,\"colors\":[...],\"receipt\":\"...\"}]}. Use the visible images, not guesses. "
                  "Do not use any other tools. This test has no robot or task success score.")
        thread = transport.request("thread/start", dict(cwd=str(output), model=config["served_model_name"],
            modelProvider="LocalBase", approvalPolicy="never", sandbox="danger-full-access",
            developerInstructions=prompt, dynamicTools=tools), 30)
        if thread["model"] != config["served_model_name"]:
            raise RuntimeError("Codex selected a different model")
        transport.request("turn/start", dict(threadId=thread["thread"]["id"],
            input=[{"type": "text", "text": "Run the two-round test now."}]), 30)
        deadline = started + args.timeout
        while time.monotonic() < deadline:
            event = transport.next_message(max(1, deadline-time.monotonic()))
            method, params = event.get("method"), event.get("params", {})
            if method == "item/tool/call":
                arguments = params["arguments"]
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                index = arguments["round"]-1
                if params["tool"] != "probe_observation" or index != len(calls) or index > 1:
                    raise RuntimeError("Unexpected probe tool/round order")
                calls.append(arguments)
                items = [{"type": "inputText", "text": f"Round {index+1}. Receipt: {expected[index]['receipt']}. Images in camera order 0,1,2:"}]
                for camera, color in enumerate(expected[index]["colors"]):
                    path = output / f"round{index+1}-camera{camera}.png"
                    Image.new("RGB", (256, 256), rgb[color]).save(path)
                    items.append({"type": "inputImage", "imageUrl": "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()})
                transport.reply(event["id"], dict(success=True, contentItems=items))
            elif method == "item/completed" and params.get("item", {}).get("type") == "agentMessage":
                messages.append(params["item"]["text"])
            elif method == "turn/completed":
                text = "\n".join(messages)
                match = re.search(r"\{.*\}", text, re.DOTALL)
                answer = json.loads(match.group()) if match else None
                result.update(status=params["turn"]["status"], text=text,
                              passed=(params["turn"]["status"] == "completed" and len(calls) == 2
                                      and answer == {"rounds": expected}))
                if not result["passed"]:
                    raise RuntimeError("Model did not pass color/receipt/two-round verification")
                break
            elif "id" in event and method:
                raise RuntimeError("Unexpected Codex request: " + method)
        else:
            raise TimeoutError("Probe deadline exceeded")
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error))
        raise
    finally:
        result["wall_seconds"] = time.monotonic()-started
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        transport.close()
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

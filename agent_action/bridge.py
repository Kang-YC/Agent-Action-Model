"""Loopback Responses-to-vLLM bridge, reusing reference tool/SSE translation."""

import argparse
import base64
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
import uuid

from hybrid_rollout.luban_direct.bridge import events, translate_request, translate_response


def image_manifest(messages: list[dict]) -> list[dict]:
    result = []
    for index, message in enumerate(messages):
        content = message.get("content")
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "image_url":
                url = block["image_url"]["url"]
                if not url.startswith("data:") or ";base64," not in url:
                    raise ValueError("This experiment accepts inline images only")
                data = base64.b64decode(url.split(",", 1)[1], validate=True)
                result.append(dict(message_index=index, size=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return result


def prepare_request(body: dict, config: dict, cache: dict) -> tuple[dict, dict]:
    request, mapping = translate_request(body, config["served_model_name"], cache)
    # Qwen's checkpoint template allows exactly one initial system message.
    system = [m["content"] for m in request["messages"] if m["role"] == "system"]
    request["messages"] = ([dict(role="system", content="\n\n".join(system))] if system else []) + [
        m for m in request["messages"] if m["role"] != "system"]
    merged = []
    for message in request['messages']:
        if (merged and message['role'] == 'assistant' and message.get('tool_calls')
                and not message.get('content') and merged[-1]['role'] == 'assistant'
                and not merged[-1].get('tool_calls')):
            merged[-1].update({k: v for k, v in message.items() if k != 'content'})
        else:
            merged.append(message)
    request['messages'] = merged
    request.update(temperature=config["temperature"], top_p=config["top_p"],
                   chat_template_kwargs={"enable_thinking": config["enable_thinking"]})
    request["max_completion_tokens"] = min(request["max_completion_tokens"], config["max_completion_tokens"])
    return request, mapping


class Bridge(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, config: dict, output: Path):
        super().__init__(("127.0.0.1", config["bridge_port"]), Handler)
        self.config = config
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.cache = {}
        self.lock = threading.Lock()
        self.upstream = f"http://{config['host']}:{config['port']}/v1/chat/completions"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def record(self, value: dict) -> None:
        with self.lock, (self.output / "requests.jsonl").open("a") as stream:
            stream.write(json.dumps(value, ensure_ascii=False) + "\n")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status: int, value: dict) -> None:
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path != "/health":
            self.respond(404, {"error": "Unknown path"})
            return
        self.respond(200, dict(model=self.server.config["served_model_name"], status="bridge_ready"))

    def do_POST(self):
        if self.path.rstrip("/") != "/v1/responses":
            self.respond(404, {"error": "Only /v1/responses is supported"})
            return
        identifier = uuid.uuid4().hex
        started = time.monotonic()
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 64*1024*1024:
                raise ValueError("Invalid request length")
            body = json.loads(self.rfile.read(length))
            request, mapping = prepare_request(body, self.server.config, self.server.cache)
            images = image_manifest(request["messages"])
            with gzip.open(self.server.output / f"{identifier}.input.json.gz", "wt") as stream:
                json.dump(dict(codex_request=body, model_request=request), stream, ensure_ascii=False)
            self.server.record(dict(event="request", id=identifier, timestamp=time.time(), images=images,
                                    tools=list(mapping), model=request["model"]))
            req = urllib.request.Request(self.server.upstream, data=json.dumps(request).encode(),
                                         headers={"Content-Type": "application/json"})
            with self.server.opener.open(req, timeout=600) as result:
                data = json.load(result)
            response = translate_response(data, mapping, self.server.config["served_model_name"], self.server.cache)
            (self.server.output / f"{identifier}.output.json").write_text(json.dumps(
                dict(upstream=data, response=response), ensure_ascii=False, indent=2))
            self.server.record(dict(event="response", id=identifier, elapsed_s=time.monotonic()-started,
                                    usage=response["usage"], output=response["output"]))
        except Exception as error:
            detail = error.read().decode(errors="replace")[:2000] if isinstance(error, urllib.error.HTTPError) else str(error)
            self.server.record(dict(event="error", id=identifier, error=detail, error_type=type(error).__name__))
            self.respond(502, {"error": {"message": detail, "type": "upstream_or_protocol_error"}})
            return
        if not body.get("stream"):
            self.respond(200, response)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for index, event in enumerate(events(response)):
                event["sequence_number"] = index
                self.wfile.write(("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n").encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.server.record(dict(event="client_disconnect", id=identifier))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/base_model.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    with Bridge(config, args.output) as server:
        print(json.dumps(dict(event="ready", port=config["bridge_port"], model=config["served_model_name"])), flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()

"""Reusable OpenAI-compatible client for the fixed local base checkpoint."""

import argparse
import base64
import json
import mimetypes
from pathlib import Path
import urllib.request


class BaseModelClient:
    def __init__(self, config_path: Path | None = None):
        path = config_path or Path(__file__).resolve().parents[1] / "configs/base_model.json"
        self.config = json.loads(path.read_text())
        self.base_url = f"http://{self.config['host']}:{self.config['port']}/v1"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def chat(self, messages: list[dict], *, tools: list[dict] | None = None,
             tool_choice="auto", max_tokens: int | None = None, timeout: float = 600) -> dict:
        body = dict(model=self.config["served_model_name"], messages=messages, stream=False,
                    temperature=self.config["temperature"], top_p=self.config["top_p"],
                    max_completion_tokens=max_tokens or self.config["max_completion_tokens"],
                    chat_template_kwargs={"enable_thinking": self.config["enable_thinking"]})
        if tools:
            body.update(tools=tools, tool_choice=tool_choice, parallel_tool_calls=False)
        request = urllib.request.Request(self.base_url + "/chat/completions", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        with self.opener.open(request, timeout=timeout) as response:
            result = json.load(response)
        if result["model"] != self.config["served_model_name"]:
            raise ValueError("Server returned a different model identity")
        return result


def image_block(path: Path) -> dict:
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in ("image/png", "image/jpeg", "image/webp"):
        raise ValueError("Expected PNG, JPEG or WebP image")
    url = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": url}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--text", required=True)
    parser.add_argument("--image", type=Path, action="append", default=[])
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    content = [{"type": "text", "text": args.text}, *[image_block(path) for path in args.image]]
    result = BaseModelClient(args.config).chat([dict(role="user", content=content)], max_tokens=args.max_tokens)
    if args.output:
        with args.output.open("x") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

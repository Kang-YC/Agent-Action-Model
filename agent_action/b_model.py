"""Pinned base model transport and auditable H0 inputs for the B harness."""

import gzip
import os

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
import json
import time
import urllib.error
from pathlib import Path

from agent_action.client import BaseModelClient
from minisweagent.models.litellm_python_model import LitellmPythonModel


class BasePythonModel(LitellmPythonModel):
    abort_exceptions = [Exception]

    def __init__(self, config_path: Path, output: Path):
        self.client = BaseModelClient(config_path)
        from agent_action.service import health

        if not health(self.client.config)["ready"]:
            raise RuntimeError("Pinned base model service is not ready")
        self.output = output
        self.index = 0
        cfg = self.client.config
        super().__init__(
            model_name="openai/" + cfg["served_model_name"],
            cost_tracking="ignore_errors",
        )

    def _prepare_messages_for_api(self, messages):
        # H0 retains text history but only the latest observation's images.
        latest = max(
            (
                i
                for i, m in enumerate(messages)
                if isinstance(m.get("content"), list)
                and any(b.get("type") == "image_path" for b in m["content"])
            ),
            default=-1,
        )
        filtered = []
        for i, message in enumerate(messages):
            message = dict(message)
            if i != latest and isinstance(message.get("content"), list):
                message["content"] = [
                    b for b in message["content"] if b.get("type") != "image_path"
                ]
            filtered.append(message)
        return super()._prepare_messages_for_api(filtered)

    def _query(self, messages, **kwargs):
        from litellm import ModelResponse
        from minisweagent.models.utils.actions_python import (
            RUN_PYTHON_TOOL,
            RUN_PYTHON_TOOL_CHOICE,
        )

        self.index += 1
        stem = self.output / f"request_{self.index:04d}"
        with gzip.open(str(stem) + ".input.json.gz", "wt") as stream:
            json.dump(
                dict(
                    messages=messages, tool=RUN_PYTHON_TOOL, config=self.client.config
                ),
                stream,
            )
        started = time.monotonic()
        try:
            response = self.client.chat(
                messages, tools=[RUN_PYTHON_TOOL], tool_choice=RUN_PYTHON_TOOL_CHOICE
            )
            Path(str(stem) + ".output.json").write_text(json.dumps(response, indent=2))
            with (self.output / "requests.jsonl").open("a") as stream:
                stream.write(
                    json.dumps(
                        dict(
                            index=self.index,
                            latency_seconds=time.monotonic() - started,
                            usage=response.get("usage"),
                            status="completed",
                        )
                    )
                    + "\n"
                )
            return ModelResponse(**response)
        except Exception as error:
            detail = (
                error.read().decode(errors="replace")
                if isinstance(error, urllib.error.HTTPError)
                else str(error)
            )
            Path(str(stem) + ".error.json").write_text(
                json.dumps(dict(error_type=type(error).__name__, detail=detail))
            )
            with (self.output / "requests.jsonl").open("a") as stream:
                stream.write(
                    json.dumps(
                        dict(
                            index=self.index,
                            latency_seconds=time.monotonic() - started,
                            status="error",
                            error=str(error),
                        )
                    )
                    + "\n"
                )
            raise

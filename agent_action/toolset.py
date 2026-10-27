"""External mini-swe-agent toolset; use RobotEnvironment for cell limits."""

import json
from pathlib import Path
import re
import hashlib

from minisweagent.environments.python_tool import PythonToolEnvironment
from minisweagent.tools.registry import ToolPrompt, ToolRegistry, ToolSpec

from agent_action.native import NativeRobot
from agent_action.robot import CONTRACT


def connect(host: str, port: int, timeout: float):
    from hybrid_rollout.robodojo.robodojo_server.protocol import RPCClient
    return RPCClient(host, port, timeout=timeout)


class RobotContext:
    def __init__(self, *, output: str, task: str, seed: int = 0,
                 host: str = "127.0.0.1", port: int = 19113, timeout: float = 600,
                 requirements=(), allowed_tools=()):
        rpc = connect(host, port, timeout)
        try:
            self.robot = NativeRobot(rpc, Path(output), task, seed)
        except BaseException:
            rpc.close()
            raise
        self.session_globals = {"_begin_robot_cell": self.robot.begin_cell,
                                "Observation": self.robot.packet}

    def close(self) -> None:
        self.robot.close()


def move_to(ctx: RobotContext, left: dict, right: dict, steps: int = 5) -> dict:
    observation = ctx.robot.move_to(left, right, steps)
    ctx.session_globals["Observation"].clear()
    ctx.session_globals["Observation"].update(observation)
    print(json.dumps(observation, ensure_ascii=False))
    for image in observation["images"]:
        print(f"{image['camera']}: <MSWEA_IMAGE_PATH>{image['path']}</MSWEA_IMAGE_PATH>")
    return observation


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolSpec(name="move_to", function=move_to, prompt=ToolPrompt(
        summary="Execute one bounded dual-arm robot action and automatically return current RGB and state.",
        parameters={"left": "Left position, quaternion_wxyz, gripper_closed dictionary.",
                    "right": "Right position, quaternion_wxyz, gripper_closed dictionary.",
                    "steps": f"Integer 1..{CONTRACT.max_steps}, default {CONTRACT.max_steps}."},
        returns="Post-ACK observation; images and state are automatically printed for the next model request.",
        raises="ValueError for invalid targets; RuntimeError for repeated calls or uncertain execution.",
        details=CONTRACT.description() + " At most one invocation per cell. Observation holds the latest state.",
        examples=("move_to(Observation['current_eef']['left'], Observation['current_eef']['right'], steps=1)",),
    )))
    return registry


class RobotEnvironment(PythonToolEnvironment):
    def execute(self, action: dict, cwd: str = "") -> dict:
        result = super().execute({**action, "code": "_begin_robot_cell()\n" + action.get("code", "")}, cwd)
        artifacts = result["extra"].setdefault("artifacts", [])
        for name in re.findall(r"<MSWEA_IMAGE_PATH>(.*?)</MSWEA_IMAGE_PATH>", result["output"]):
            path = Path(name)
            content = path.read_bytes()
            artifacts.append(dict(path=str(path), mime_type="image/png", size=len(content),
                                  sha256=hashlib.sha256(content).hexdigest()))
        return result

"""Single-owner reference RPC adapter; never retries uncertain actions."""

from dataclasses import asdict
import json
from pathlib import Path
import time
import uuid

import numpy as np
from PIL import Image

from agent_action.robot import CONTRACT


def save_json(path: Path, value: dict) -> None:
    def encode(item):
        if isinstance(item, np.ndarray):
            return item.tolist()
        if isinstance(item, np.generic):
            return item.item()
        raise TypeError(type(item).__name__)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, default=encode, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


class NativeRobot:
    def __init__(self, rpc, output: Path, task: str, seed: int = 0):
        self.rpc = rpc
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.episode = None
        self.tick = 0
        self.finished = False
        self.uncertain = False
        self.closed = False
        self.cell_used = False
        self.index = 0
        self.gripper_commands = None
        self.metadata = self.rpc.request("metadata")
        CONTRACT.check_metadata(self.metadata)
        if self.metadata["task"] != task:
            raise ValueError("Launched task differs from requested task")
        reset = self.rpc.request("reset", seed=seed, source="gpt_eef", policy_version="agent_action_direct_v1")
        self.episode, self.tick = reset["episode_id"], reset["step_id"]
        self.request("switch_control_source", source="gpt_eef", reason="Agent-Action fixed EEF controller")
        save_json(self.output / "run.json", dict(contract=asdict(CONTRACT), metadata=self.metadata, reset=reset))
        self.observe()

    def request(self, op: str, **kwargs):
        if self.uncertain:
            raise RuntimeError("Uncertain native state; inspect backend records, never resend")
        try:
            return self.rpc.request(op, episode_id=self.episode, step_id=self.tick, **kwargs)
        except Exception as error:
            self.uncertain = True
            save_json(self.output / "uncertain.json", dict(op=op, episode_id=self.episode,
                      last_ack_step=self.tick, error_type=type(error).__name__, error=str(error),
                      automatic_retry=False, receipt_query_supported=False))
            raise

    def observe(self) -> dict:
        observation = self.request("teacher_observation")
        directory = self.output / f"observation_{self.index:04d}"
        directory.mkdir()
        np.savez_compressed(directory / "raw.npz", **observation)
        images = []
        for camera in CONTRACT.cameras:
            path = directory / f"{camera}.png"
            Image.fromarray(observation[camera]).save(path)
            images.append(dict(camera=camera, path=str(path)))
        self.current = {arm: dict(position=observation["eef_positions"][i].tolist(),
                        quaternion_wxyz=observation["eef_quaternions_wxyz"][i].tolist(),
                        gripper_closed=(self.gripper_commands[arm] if self.gripper_commands is not None
                                        else bool(observation["states"][i*7+6] < .5)))
                        for i, arm in enumerate(("left", "right"))}
        self.packet = dict(episode_id=self.episode, step_id=self.tick, current_eef=self.current,
                           instruction=observation["instruction"], images=images,
                           remaining_steps=observation["remaining_steps"],
                           rollout_finished=self.finished,
                           native_gripper_opening_feedback=[float(observation["states"][i*7+6]) for i in range(2)],
                           gripper_state_kind=("last_acknowledged_command" if self.gripper_commands is not None
                                               else "initial_native_feedback_estimate"))
        save_json(directory / "observation.json", self.packet)
        return self.packet

    def begin_cell(self) -> None:
        self.cell_used = False

    def move_to(self, left: dict, right: dict, steps: int = 5) -> dict:
        if self.finished or self.uncertain:
            raise RuntimeError("Episode finished or native state uncertain")
        if self.cell_used:
            raise RuntimeError("At most one move_to invocation per Python cell")
        self.cell_used = True
        targets = CONTRACT.validate(left, right, steps, self.current)
        self.index += 1
        path = self.output / f"action_{self.index:04d}.json"
        record = dict(request_id=uuid.uuid4().hex, start_step=self.tick, targets=targets,
                      requested_steps=steps, started_at_unix=time.time(), receipts=[])
        save_json(path, record)
        try:
            for _ in range(steps):
                proposal = self.request("eef_joint_target", targets=targets)
                receipt = self.request("chunk_step", actions=np.asarray([proposal["action"]], np.float32),
                                       teacher_request_id=record["request_id"])
                record["receipts"].append(dict(proposal=proposal, result=receipt))
                save_json(path, record)
                if receipt["episode_id"] != self.episode or receipt["step_id"] != self.tick + 1:
                    self.uncertain = True
                    raise RuntimeError("Unexpected native execution receipt")
                self.tick = receipt["step_id"]
                rows = receipt["steps"]
                if len(rows) != 1 or not rows[0]["valid"]:
                    self.uncertain = True
                    raise RuntimeError("Expected exactly one valid native control ACK")
                self.gripper_commands = {arm: targets[arm]["gripper_closed"] for arm in targets}
                if rows[0]["terminated"] or rows[0]["truncated"]:
                    self.finished = True
                    break
            packet = self.observe()
            packet["execution_feedback"] = dict(requested_steps=steps, executed_steps=self.tick-record["start_step"],
                                                 status="acknowledged")
            save_json(self.output / f"observation_{self.index:04d}" / "observation.json", packet)
            record.update(end_step=self.tick, finished_at_unix=time.time(), status="acknowledged")
            save_json(path, record)
            # Success labels stay in evaluator logs, outside the agent-facing packet.
            return packet
        except Exception as error:
            self.uncertain = True
            record.update(status="uncertain",
                          error_type=type(error).__name__, error=str(error))
            save_json(path, record)
            raise

    def close(self, reason: str = "controller_close") -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.episode is not None and not self.uncertain:
                save_json(self.output / "result.json", self.request("finish_pilot", reason=reason))
        finally:
            self.rpc.close()

"""B-line CLI: mini-swe-agent, persistent Python and bounded native robot tools."""

import argparse
import json
from pathlib import Path
import subprocess
import hashlib
import shutil
import time

from minisweagent.agents.default import DefaultAgent
from minisweagent.exceptions import LimitsExceeded
from agent_action.b_model import BasePythonModel, ContextLimitExceeded
from agent_action.toolset import RobotEnvironment
from agent_action.b_report import summarize


class RobotAgent(DefaultAgent):
    def query(self):
        packets = sorted(self.robot_output.glob("observation_*/observation.json"))
        packet = json.loads(packets[-1].read_text())
        reason = None
        if (self.robot_output / "uncertain.json").exists():
            reason = "uncertain_execution"
        elif packet["rollout_finished"]:
            reason = "native_terminal"
        elif packet["step_id"] >= self.control_limit:
            reason = "control_budget"
        elif self.token_limit and self.tokens() >= self.token_limit:
            reason = "token_budget"

        if reason:
            raise LimitsExceeded(
                dict(
                    role="exit",
                    content=reason,
                    extra=dict(exit_status=reason, submission=""),
                )
            )
        return super().query()

    def tokens(self):
        log = self.model.output / "requests.jsonl"
        return (
            sum(
                (json.loads(line).get("usage") or {}).get("total_tokens", 0)
                for line in log.read_text().splitlines()
            )
            if log.exists()
            else 0
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path("configs/base_model.json"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--task", default="classify_objects")
    p.add_argument(
        "--sim-output", type=Path, help="Evaluator-only native outcome directory"
    )
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--port", type=int, default=19123)
    p.add_argument("--max-turns", type=int, default=10, help="Model call limit; 0 disables")
    p.add_argument("--max-control-steps", type=int, default=10)
    p.add_argument("--max-total-tokens", type=int, default=200000)
    p.add_argument("--wall-seconds", type=int, default=1800, help="Agent wall limit; 0 disables")
    p.add_argument("--history-turns", type=int, default=0,
                   help="Explicit recent text exchanges to retain; 0 keeps all text")
    a = p.parse_args()
    if (
        a.max_control_steps <= 0
        or min(a.max_turns, a.wall_seconds, a.max_total_tokens, a.history_turns) < 0
    ):
        p.error("Control steps must be positive; other budgets must be non-negative")
    output = a.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    model_config = json.loads(a.config.read_text())
    robot_output = output / "robot"
    manifest = dict(
        arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(a).items()},
        model=model_config,
        history="H0_latest_images_all_text" if not a.history_turns else f"H0_latest_images_recent_{a.history_turns}_turns",
        mini_revision=subprocess.check_output(
            ["git", "-C", "third_party/mini-swe-agent", "rev-parse", "HEAD"], text=True
        ).strip(),
    )
    sources = {}
    for root in (
        Path("agent_action"),
        Path("third_party/mini-swe-agent/src/minisweagent"),
    ):
        for source in root.rglob("*.py"):
            target = output / "source" / source
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            sources[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest["sources_sha256"] = sources
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    started = time.monotonic()
    report = dict(status="infrastructure_error")
    try:
        model = BasePythonModel(a.config, output, history_turns=a.history_turns)
        with RobotEnvironment(
            toolset="agent_action.toolset:build_registry",
            context_factory="agent_action.toolset:RobotContext",
            context_kwargs=dict(
                output=str(robot_output),
                task=a.task,
                seed=a.seed,
                port=a.port,
                max_control_steps=a.max_control_steps,
            ),
            memory_limit_gb=0,
            startup_timeout=600,
            timeout=600,
            artifact_dir=output / "python",
            keep_session_dir=True,
        ) as env:
            init = env.execute(dict(code="print('Robot session ready')"))
            if init["returncode"]:
                raise RuntimeError(init["output"])
            packet = json.loads(
                (robot_output / "observation_0000/observation.json").read_text()
            )
            packet["remaining_control_budget"] = a.max_control_steps - packet["step_id"]
            task = (
                json.dumps(packet)
                + "\n"
                + "\n".join(
                    "<MSWEA_IMAGE_PATH>" + im["path"] + "</MSWEA_IMAGE_PATH>"
                    for im in packet["images"]
                )
            )
            agent = RobotAgent(
                model,
                env,
                step_limit=a.max_turns,
                cost_limit=0,
                wall_time_limit_seconds=a.wall_seconds,
                output_path=output / "trajectory.json",
                system_template="Control a dual-arm robot using only the documented move_to function. "
                "Every response must be exactly one run_python call, with a complete Python cell. "
                "Python variables persist. Observation holds the current measured state. "
                "Initial and post-action camera images are provided automatically. "
                "Only the latest three images are shown. Before moving again, record useful visually "
                "observed facts in Python variables and print them; do not assume older images remain visible. "
                "At most one move_to invocation per cell, including rejected calls. "
                "Put direct Python code in the tool argument; never call run_python inside the cell. "
                'For a hold example: move_to(Observation["current_eef"]["left"], '
                'Observation["current_eef"]["right"], steps=1). '
                "Use only supplied images, state and instruction; do not inspect files or evaluator data. "
                "Do not infer grasp success from the gripper command. "
                "Continue until native termination or runner budget. ReturnAnswer is a model stop, not task success. "
                "Do not reset or restart episodes.\n{{ tool_prompt }}",
                instance_template="{{ task }}",
            )
            agent.robot_output, agent.control_limit, agent.token_limit = (
                robot_output,
                a.max_control_steps,
                a.max_total_tokens,
            )
            try:
                result = agent.run(task)
                report.update(
                    status=result["exit_status"],
                    model_calls=agent.n_calls,
                    total_tokens=agent.tokens(),
                )
            except ContextLimitExceeded:
                report["status"] = "context_limit"
                raise
            finally:
                reason = {
                    "control_budget": "control_step_budget",
                    "LimitsExceeded": "decision_budget",
                }.get(report["status"], report["status"])
                (robot_output / "controller_stop.json").write_text(
                    json.dumps(dict(reason=reason))
                )
    except Exception as error:
        report.update(
            controller_status=report["status"],
            status="context_limit" if isinstance(error, ContextLimitExceeded) else "infrastructure_error",
            error_type=type(error).__name__,
            error=str(error),
        )
        raise
    finally:
        report.update(
            summarize(output, status=report["status"], sim_output=a.sim_output)
        )
        report["wall_seconds"] = time.monotonic() - started
        (output / "summary.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

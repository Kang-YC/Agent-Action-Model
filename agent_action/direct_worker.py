"""Reference policy/tools with explicit local development budget termination."""

import argparse
from pathlib import Path
import signal
import time

from hybrid_rollout.luban_direct.worker import LubanPolicy
from hybrid_rollout.robodojo.io import write_json
from hybrid_rollout.robodojo.robodojo_server.gpt_only_client import GPTOnlyTools


TOKEN_BUDGET_ERROR = "Configured total-token budget reached; stopping this episode"


class RolloutFinished(Exception):
    """The final tool result was delivered; no further model turns are needed."""


class StopAfterFinish:
    def __init__(self, transport, rollout):
        self.transport = transport
        self.rollout = rollout

    def __getattr__(self, name):
        return getattr(self.transport, name)

    def reply(self, identifier, result):
        self.transport.reply(identifier, result)
        if self.rollout.phase == "done":
            raise RolloutFinished()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task", default="classify_objects")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--sim-port", type=int, required=True)
    parser.add_argument("--max-decisions", type=int, required=True)
    parser.add_argument("--max-control-steps", type=int, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    policy = rollout = None
    started = time.monotonic()

    def interrupted(*_):
        raise KeyboardInterrupt("Stopping owned controller")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        policy = LubanPolicy(output / "codex_workspace", args.codex)
        rollout = GPTOnlyTools(output, args.task, sim_port=args.sim_port, seed=args.seed,
                               max_decisions=args.max_decisions, max_control_steps=args.max_control_steps,
                               prompt_sha256=policy.prompt_sha256)
        policy.transport = StopAfterFinish(policy.transport, rollout)
        policy.run(rollout)
    except RolloutFinished:
        write_json(output / "termination.json", dict(reason="native_runner_finished", step_id=rollout.tick))
    except BaseException as error:
        budget = isinstance(error, RuntimeError) and str(error) == TOKEN_BUDGET_ERROR
        reason = "token_budget" if budget else "operator_interrupt" if isinstance(error, KeyboardInterrupt) else "controller_error"
        write_json(output / "termination.json", dict(reason=reason, error_type=type(error).__name__,
                                                     error=str(error), step_id=rollout.tick if rollout else None))
        if rollout and rollout.episode and rollout.phase != "done":
            try:
                rollout.finish(reason)
            except Exception as cleanup_error:
                write_json(output / "cleanup_error.json", dict(error=str(cleanup_error)))
                raise
        if not budget:
            raise
    finally:
        write_json(output / "timing.json", dict(wall_seconds=time.monotonic()-started))
        if rollout:
            rollout.close()
        if policy:
            policy.close()


if __name__ == "__main__":
    main()

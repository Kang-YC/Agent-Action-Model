"""Real base / mini-swe-agent persistent Python / multimodal feedback probe."""

import argparse
import json
from pathlib import Path
import secrets

from PIL import Image
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.python_tool import PythonToolEnvironment
from minisweagent.tools.registry import ToolRegistry
from agent_action.b_model import BasePythonModel


def empty_registry():
    return ToolRegistry()


class ProbeContext:
    def __init__(self, *, output, requirements=(), allowed_tools=()):
        output = Path(output)
        colors = ["red", "green", "blue"]
        secrets.SystemRandom().shuffle(colors)
        orders = [colors, colors[1:] + colors[:1]]
        rgb = dict(red=(235, 25, 25), green=(25, 190, 25), blue=(25, 25, 235))
        rounds = []
        self.expected = []
        for r, order in enumerate(orders):
            paths = []
            for i, color in enumerate(order):
                path = output / f"r{r}-camera{i}.png"
                Image.new("RGB", (160, 160), rgb[color]).save(path)
                paths.append(str(path))
            receipt = secrets.token_hex(8)
            rounds.append(dict(paths=paths, receipt=receipt))
            self.expected.append(dict(round=r + 1, colors=order, receipt=receipt))
        (output / "expected.json").write_text(json.dumps(self.expected))

        def observe(round):
            if round != len(self.calls) + 1 or round not in (1, 2):
                raise ValueError("Request rounds 1 then 2, once each")
            self.calls.append(round)
            entry = rounds[round - 1]
            print("Receipt:", entry["receipt"])
            return [Image.open(path).copy() for path in entry["paths"]]

        self.calls = []
        self.session_globals = dict(probe_observation=observe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/base_model.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    model = BasePythonModel(args.config, output)
    with PythonToolEnvironment(
        toolset="agent_action.b_probe:empty_registry",
        context_factory="agent_action.b_probe:ProbeContext",
        context_kwargs=dict(output=str(output)),
        memory_limit_gb=0,
        artifact_dir=output / "python",
        keep_session_dir=True,
    ) as env:
        agent = DefaultAgent(
            model,
            env,
            step_limit=5,
            cost_limit=0,
            output_path=output / "trajectory.json",
            system_template="You use persistent Python. Respond with exactly one run_python call per turn. "
            "show(image) returns visual evidence; ReturnAnswer(string) submits your answer. "
            "probe_observation(round) returns three PIL images and prints a random receipt. "
            "Call it for round=1, show all three images in list order. On the next turn call round=2 "
            "and show its three images. Remember the colors and receipts of both rounds. "
            "The first cell should be: cards = probe_observation(round=1); [show(card) for card in cards]. "
            "H0 only supplies the newest three images. Before calling round=2, store your visually inferred "
            "round-1 colors and receipt in a persistent Python variable and print it. Do not postpone "
            "reading round-1 colors until after round=2 replaces the images. Then call "
            "cards = probe_observation(round=2); [show(card) for card in cards]. "
            "Do not call run_python inside Python. Call each observation only once and store the result. "
            'Finally ReturnAnswer a JSON string: {"rounds":[{"round":1,"colors":[...],"receipt":"..."},'
            '{"round":2,"colors":[...],"receipt":"..."}]}. Use basic English color names.',
            instance_template="Run the two-round test now.",
        )
        result = agent.run()
    expected = json.loads((output / "expected.json").read_text())
    try:
        answer = json.loads(result.get("submission", ""))
    except (ValueError, TypeError):
        answer = None
    report = dict(
        passed=answer == dict(rounds=expected),
        result=result,
        answer=answer,
        model=model.client.config["served_model_name"],
        api_calls=agent.n_calls,
    )
    (output / "result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

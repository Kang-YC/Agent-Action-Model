"""Small Codex Direct development run using the reference policy and tools."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

from agent_action.serve import checkpoint_manifest


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--config", type=Path, default=root / "configs/base_model.json")
    parser.add_argument("--reference", type=Path, default=root.parent / "GPT-as-Policy")
    parser.add_argument("--robodojo", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task", default="classify_objects")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--sim-port", type=int, default=19124)
    parser.add_argument("--max-decisions", type=int, default=2)
    parser.add_argument("--max-control-steps", type=int, default=10)
    parser.add_argument("--wall-seconds", type=int, default=900)
    parser.add_argument("--max-total-tokens", type=int, default=200000)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "sim").mkdir()
    (output / "logs").mkdir()
    (output / "codex_home").mkdir()
    snapshot = output / "reference_source"
    (snapshot / "hybrid_rollout").mkdir(parents=True)
    shutil.copy2(args.reference / "hybrid_rollout/__init__.py", snapshot / "hybrid_rollout/__init__.py")
    for name in ("robodojo", "luban_direct"):
        shutil.copytree(args.reference / "hybrid_rollout" / name, snapshot / "hybrid_rollout" / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    harness_source = output / "harness_source"
    (harness_source / "agent_action").mkdir(parents=True)
    for name in ("__init__.py", "direct.py", "direct_worker.py", "bridge.py", "serve.py"):
        shutil.copy2(root / "agent_action" / name, harness_source / "agent_action" / name)
    (harness_source / "scripts").mkdir()
    shutil.copy2(root / "scripts/start_native.sh", harness_source / "scripts/start_native.sh")
    shutil.copy2(args.config, output / "base_model.json")
    manifest = checkpoint_manifest(config)
    manifest.update(kind="development_direct_chain_validation", task=args.task, layout_id=args.seed,
                    max_decisions=args.max_decisions, max_control_steps=args.max_control_steps,
                    max_total_tokens=args.max_total_tokens,
                    wall_seconds=args.wall_seconds, simulation_pauses_for_inference=True,
                    inference_config=config, codex_version=subprocess.check_output([str(args.codex), "--version"], text=True).strip(),
                    codex_sha256=hashlib.sha256(args.codex.read_bytes()).hexdigest(),
                    effective_codex_context_window=config["max_model_len"],
                    harness_commit=subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
                    harness_sources={str(p.relative_to(harness_source)): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in harness_source.rglob("*") if p.is_file()},
                    reference_sources={str(p.relative_to(snapshot)): hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in snapshot.rglob("*") if p.is_file()})
    for name, repo in (("reference", args.reference), ("robodojo", args.robodojo)):
        manifest[name + "_commit"] = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        (output / f"{name}.patch").write_text(subprocess.check_output(["git", "-C", str(repo), "diff"], text=True))
    write(output / "manifest.json", manifest)
    # The upstream worker hardcodes a 128K context. Override only Codex's budget
    # flags at the executable boundary; all reference prompts/tools stay intact.
    wrapper = output / "codex-with-local-context.sh"
    wrapper.write_text("#!/bin/sh\nif [ \"${1:-}\" = app-server ]; then\n  exec " + shlex.quote(str(args.codex.resolve())) +
        ' "$@" -c model_context_window=' + str(config["max_model_len"]) +
        " -c model_auto_compact_token_limit=" + str(config["max_model_len"]*3//4) +
        "\nfi\nexec " + shlex.quote(str(args.codex.resolve())) + ' "$@"\n')
    wrapper.chmod(0o755)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (output / "harness_source", snapshot))),
               PYTHONUNBUFFERED="1", GPT_AS_POLICY_ROOT=str(snapshot), ROBODOJO_ROOT=str(args.robodojo.resolve()),
               ROBODOJO_SOURCE=str(args.robodojo.resolve()), CODEX_HOME=str(output / "codex_home"),
               ROLLOUT_MODEL=config["served_model_name"], ROLLOUT_MODEL_PROVIDER="LocalBase",
               ROLLOUT_REASONING_EFFORT="", ROLLOUT_MODEL_BASE_URL=f"http://127.0.0.1:{config['bridge_port']}/v1",
               CODEX_MAX_TOTAL_TOKENS=str(args.max_total_tokens), NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY", "LUBAN_API_KEY"):
        env.pop(key, None)
    children, logs = [], []
    started = time.monotonic()
    summary = dict(status="infrastructure_error", formal_evaluation=False)

    def start(name, command):
        log = (output / "logs" / f"{name}.log").open("w")
        logs.append(log)
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        children.append(process)
        return process

    def interrupted(*_):
        raise KeyboardInterrupt("Stopping owned development processes")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        # The model service has its own lifecycle; this runner owns only its children.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{config['port']}/v1/models", timeout=10) as response:
            if config["served_model_name"] not in [m["id"] for m in json.load(response)["data"]]:
                raise ValueError("The expected local base is not served")
        bridge = start("bridge", [sys.executable, "-m", "agent_action.bridge", "--config", str(args.config.resolve()),
                                  "--output", str(output / "model_requests")])
        sim = start("sim", ["bash", str(harness_source / "scripts/start_native.sh"), "--task", args.task,
                            "--port", str(args.sim_port), "--output", str(output / "sim")])
        while '"event": "ready"' not in (output / "logs/sim.log").read_text(errors="replace"):
            if sim.poll() is not None or bridge.poll() is not None:
                raise RuntimeError("Service exited during startup; inspect logs")
            if time.monotonic()-started > min(300, args.wall_seconds):
                raise TimeoutError("Service startup deadline")
            time.sleep(1)
        with opener.open(f"http://127.0.0.1:{config['bridge_port']}/health", timeout=10):
            pass
        worker = start("controller", [sys.executable, "-m", "agent_action.direct_worker",
            "--codex", str(wrapper), "--output", str(output / "controller"), "--task", args.task,
            "--seed", str(args.seed), "--sim-port", str(args.sim_port), "--max-decisions", str(args.max_decisions),
            "--max-control-steps", str(args.max_control_steps)])
        code = worker.wait(timeout=max(1, args.wall_seconds-(time.monotonic()-started)))
        if code:
            summary["status"] = "controller_error"
            raise RuntimeError(f"Reference controller exited {code}; inspect logs")
        result = json.loads((output / "controller/result.json").read_text())
        summary.update(status="budget_censored" if result["reason"] == "token_budget" else "completed", result=result)
    except BaseException as error:
        summary.update(error_type=type(error).__name__, error=str(error))
        raise
    finally:
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
        for log in logs:
            log.close()
        summary["wall_seconds"] = time.monotonic()-started
        if (output / "sim/evaluation_outcome.json").exists():
            summary["native_outcome"] = json.loads((output / "sim/evaluation_outcome.json").read_text())
        write(output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

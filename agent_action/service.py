"""Idempotent lifecycle management for the pinned local base model service."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

from agent_action.serve import server_arguments

ROOT = Path(__file__).resolve().parents[1]


def process_identity(pid: int) -> dict | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except FileNotFoundError:
        return None
    if stat[0] == "Z":
        return None
    return dict(pid=pid, start_ticks=stat[19], argv=[s.decode() for s in command if s])


def matches_process(state: dict) -> bool:
    identity = process_identity(state["pid"])
    return identity is not None and identity["start_ticks"] == state["start_ticks"] and identity["argv"] == state["argv"]


def config_hash(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def health(config: dict) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{config['host']}:{config['port']}/v1/models", timeout=3) as response:
            models = json.load(response)["data"]
    except (OSError, urllib.error.URLError):
        return {"ready": False}
    selected = [m for m in models if m["id"] == config["served_model_name"]]
    if len(selected) != 1 or Path(selected[0]["root"]).resolve() != Path(config["checkpoint"]).resolve():
        raise RuntimeError("Endpoint serves a different model/checkpoint; refusing reuse")
    return dict(ready=True, model=selected[0]["id"], checkpoint=selected[0]["root"])


def verify_adoption(pid: int, config: dict) -> dict:
    identity = process_identity(pid)
    if identity is None:
        raise ValueError("Process is not running")
    argv = identity["argv"]
    if "vllm.entrypoints.cli.main" not in argv or "serve" not in argv:
        raise ValueError("PID is not a vLLM CLI model server")
    if argv[argv.index("serve"):] != server_arguments(config):
        raise ValueError("Running process arguments differ from the pinned configuration")
    if not health(config)["ready"]:
        raise ValueError("Cannot adopt a server that is not ready")
    return identity


@contextmanager
def service_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "service.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def write_state(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def status(config: dict, state: dict | None) -> dict:
    ready = health(config)
    if state is None:
        return dict(status="unmanaged_ready" if ready["ready"] else "stopped", **ready)
    if state["config_sha256"] != config_hash(config):
        raise ValueError("Configuration changed; stop the old service before changing its configuration")
    alive = matches_process(state)
    return dict(status="ready" if alive and ready["ready"] else "starting" if alive else "stale_state",
                managed=alive, pid=state["pid"], base_url=state["base_url"], log=state["log"], **ready)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/base_model.json")
    parser.add_argument("--state-dir", type=Path, default=ROOT / "artifacts/base-service")
    sub = parser.add_subparsers(dest="action", required=True)
    start = sub.add_parser("start")
    start.add_argument("--wait", action="store_true")
    start.add_argument("--timeout", type=int, default=600)
    start.add_argument("--python", type=Path, default=Path(os.environ.get("BASE_MODEL_PYTHON", ROOT / ".venv-inference/bin/python")))
    adopt = sub.add_parser("adopt")
    adopt.add_argument("--pid", type=int, required=True)
    adopt.add_argument("--log", type=Path, required=True)
    sub.add_parser("status")
    stop = sub.add_parser("stop")
    stop.add_argument("--timeout", type=int, default=30)
    logs = sub.add_parser("logs")
    logs.add_argument("--lines", type=int, default=30)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    directory = args.state_dir.resolve()
    state_path = directory / "service.json"
    with service_lock(directory):
        state = json.loads(state_path.read_text()) if state_path.exists() else None
        if args.action == "adopt":
            if state and matches_process(state) and state["pid"] != args.pid:
                raise ValueError("A different managed service is running")
            identity = verify_adoption(args.pid, config)
            state = dict(**identity, config_sha256=config_hash(config),
                         base_url=f"http://{config['host']}:{config['port']}/v1", log=str(args.log.resolve()), adopted=True)
            write_state(state_path, state)
        elif args.action == "start":
            current = status(config, state)
            if current["status"] == "unmanaged_ready":
                raise ValueError("An unregistered server is running; adopt its verified PID first")
            if not state or not matches_process(state):
                if health(config)["ready"]:
                    raise ValueError("Endpoint is owned by an unregistered process")
                stamp = time.strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}"
                run_dir = directory / stamp
                run_dir.mkdir()
                env = dict(os.environ, PYTHONPATH=str(ROOT), TOKENIZERS_PARALLELISM="false",
                           VLLM_NO_USAGE_STATS="1", DO_NOT_TRACK="1")
                with (run_dir / "model.log").open("w") as log:
                    child = subprocess.Popen([str(args.python.absolute()), "-m", "agent_action.serve", "--config", str(args.config.resolve()),
                        "--output", str(run_dir / "runtime.json")], cwd=ROOT, env=env,
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                identity = process_identity(child.pid)
                if identity is None:
                    raise RuntimeError(f"Model server exited; inspect {run_dir / 'model.log'}")
                # exec changes argv during startup, so persist only after the launcher execs vLLM.
                deadline = time.monotonic() + 30
                while identity and "vllm.entrypoints.cli.main" not in identity["argv"]:
                    if time.monotonic() > deadline:
                        child.terminate()
                        child.wait(timeout=10)
                        raise TimeoutError("Launcher did not exec vLLM within 30 seconds")
                    time.sleep(.2)
                    identity = process_identity(child.pid)
                if identity is None:
                    raise RuntimeError(f"Model server exited; inspect {run_dir / 'model.log'}")
                state = dict(**identity, config_sha256=config_hash(config),
                             base_url=f"http://{config['host']}:{config['port']}/v1", log=str(run_dir / "model.log"), adopted=False)
                write_state(state_path, state)
        elif args.action == "stop":
            if state and matches_process(state):
                os.kill(state["pid"], signal.SIGTERM)
                deadline = time.monotonic() + args.timeout
                while matches_process(state):
                    if time.monotonic() > deadline:
                        raise TimeoutError("Service has not stopped; inspect logs before retrying")
                    time.sleep(.2)
            elif health(config)["ready"]:
                raise ValueError("Refusing to stop an unregistered or different process")
            if state_path.exists():
                state_path.rename(directory / f"stopped-{time.time_ns()}.json")
            print(json.dumps(dict(status="stopped")))
            return
        elif args.action == "logs":
            if not state:
                raise ValueError("No registered service log")
            print("\n".join(Path(state["log"]).read_text(errors="replace").splitlines()[-args.lines:]))
            return
        result = status(config, state)
    if args.action == "start" and args.wait:
        deadline = time.monotonic() + args.timeout
        while result["status"] == "starting":
            if time.monotonic() > deadline:
                raise TimeoutError(f"Readiness timeout; process retained, inspect {state['log']}")
            time.sleep(1)
            result = status(config, state)
        if result["status"] != "ready":
            raise RuntimeError(f"Service failed: {result}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

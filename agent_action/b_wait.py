"""Wait for recorded A-line processes and GPU space, then run one B smoke."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from agent_action.service import health, matches_process, process_identity, write_state


def free_gpu_mib() -> int:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    )
    values = [int(v.strip()) for v in result.stdout.splitlines() if v.strip()]
    if len(values) != 1:
        raise RuntimeError("Expected the single visible GPU used by the pinned service")
    return values[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wait-pid", type=int, action="append", required=True)
    p.add_argument(
        "--output", type=Path, required=True, help="New waiting-state directory"
    )
    p.add_argument("--run-output", type=Path, required=True)
    p.add_argument("--config", type=Path, default=Path("configs/base_model.json"))
    p.add_argument("--timeout", type=int, default=21600)
    p.add_argument("--min-free-mib", type=int, default=7500)
    a = p.parse_args()
    output = a.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run_output = a.run_output.resolve()
    if run_output.exists():
        raise ValueError("Run output must not exist")
    cfg = json.loads(a.config.read_text())
    processes = [
        identity
        for pid in a.wait_pid
        if (identity := process_identity(pid)) is not None
    ]
    for identity in processes:
        if not any(
            value
            in ("agent_action.direct", "hybrid_rollout.robodojo.robodojo_server.server")
            for value in identity["argv"]
        ):
            raise ValueError("Wait target is not an A-line launcher or native backend")
    state = dict(
        status="waiting_for_A",
        pid=os.getpid(),
        wait_processes=processes,
        run_output=str(run_output),
        started_at_unix=time.time(),
        command=[
            "bash",
            "scripts/run_b_line.sh",
            str(run_output),
            "--config",
            str(a.config.resolve()),
            "--max-turns",
            "10",
            "--max-control-steps",
            "10",
            "--max-total-tokens",
            "200000",
            "--wall-seconds",
            "1800",
        ],
        policy="Wait only; never stop or alter A-line processes",
    )
    state_path = output / "state.json"
    write_state(state_path, state)
    child = None
    started = time.monotonic()

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        while True:
            alive = [s["pid"] for s in processes if matches_process(s)]
            free = free_gpu_mib()
            state.update(
                waiting_pids=alive, free_gpu_mib=free, updated_at_unix=time.time()
            )
            if time.monotonic() - started >= a.timeout:
                state["status"] = "resource_wait_timeout"
                break
            if not alive and free >= a.min_free_mib:
                if not health(cfg)["ready"]:
                    raise RuntimeError("Pinned base service is no longer ready")
                state["status"] = "running_smoke"
                write_state(state_path, state)
                env = dict(
                    os.environ,
                    ROBODOJO_ROOT=os.environ.get(
                        "ROBODOJO_ROOT",
                        "/dataset_rc_b1/kangyc1@xiaopeng.com/robodojo_shared/RoboDojo",
                    ),
                )
                with (output / "run.log").open("w") as log:
                    child = subprocess.Popen(
                        state["command"],
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    state["child_pid"] = child.pid
                    write_state(state_path, state)
                    deadline = time.monotonic() + 3600
                    while child.poll() is None:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                "B smoke exceeded its outer wall-clock budget"
                            )
                        time.sleep(5)
                state.update(
                    status="smoke_finished"
                    if child.returncode == 0
                    else "smoke_failed",
                    returncode=child.returncode,
                )
                summary = run_output / "controller/summary.json"
                if summary.exists():
                    state["smoke_summary"] = json.loads(summary.read_text())
                # Development/full evaluation needs inspection of the actual smoke evidence.
                state["next_step"] = (
                    "Review smoke, then run the development episode; no batch evaluation launched"
                )
                break
            write_state(state_path, state)
            time.sleep(10)
    except (Exception, KeyboardInterrupt) as error:
        state.update(
            status="interrupted" if isinstance(error, KeyboardInterrupt) else "error",
            error_type=type(error).__name__,
            error=str(error),
        )
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        state["updated_at_unix"] = time.time()
        write_state(state_path, state)
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()

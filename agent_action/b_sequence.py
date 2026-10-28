"""Run an explicitly prepared B sequence once, after the development episode ends."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time

from agent_action.b_case import ROOT, verify_prepared
from agent_action.service import health, process_identity


def prerequisite_status(run: Path) -> str:
    state_path = Path(str(run) + ".state.json")
    if not state_path.exists():
        return "missing_prerequisite_state"
    state = json.loads(state_path.read_text())
    if state.get("host") != socket.gethostname():
        return "prerequisite_host_unverified"
    if state.get("status") in ("running", "starting"):
        pid = process_identity(state["pid"])
        if pid and any(run.name + ".supervisor.py" in arg for arg in pid["argv"]):
            return "waiting"
        return "prerequisite_stopped_without_final_state"
    summary_path = run / "controller/summary.json"
    if not summary_path.exists():
        return "prerequisite_missing_summary"
    summary = json.loads(summary_path.read_text())
    native = summary.get("native_outcome") or {}
    if (state.get("status") == "finished" and native.get("complete") is True
            and native.get("valid_for_success_rate") is True):
        return "ready"
    return "prerequisite_not_native_complete"


def check_sources(expected: dict):
    for relative, checksum in expected.items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Queued source changed: {relative}; no silent protocol switch")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sequence", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    args = p.parse_args()
    definition = json.loads(args.sequence.read_text())
    if args.state.exists():
        raise FileExistsError("Queue state exists; no automatic resume or duplicate attempts")
    state = dict(status="waiting", host=socket.gethostname(), pid=os.getpid(),
                 started_at=time.time(), prerequisite=definition["prerequisite"], cases=[],
                 sequence_sha256=hashlib.sha256(args.sequence.read_bytes()).hexdigest())
    def save():
        state["updated_at"] = time.time()
        temporary = args.state.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2))
        temporary.replace(args.state)
    def interrupted(signum, frame):
        raise KeyboardInterrupt("User interrupted queued follow-up")
    signal.signal(signal.SIGTERM, interrupted)
    child = None
    save()
    try:
        while True:
            gate = prerequisite_status(Path(definition["prerequisite"]))
            state["prerequisite_status"] = gate
            save()
            if gate != "waiting":
                break
            time.sleep(10)
        if gate != "ready":
            state.update(status="halted", reason=gate)
            return
        for index, selected in enumerate(definition["cases"]):
            check_sources(definition["source_sha256"])
            plan_file = Path(selected["plan_file"])
            if hashlib.sha256(plan_file.read_bytes()).hexdigest() != selected["plan_file_sha256"]:
                raise ValueError("Queued case plan changed")
            record = json.loads(plan_file.read_text())
            verify_prepared(record)
            config = json.loads((ROOT / "configs/base_model.json").read_text())
            if not health(config)["ready"]:
                raise RuntimeError("Pinned model is not ready")
            # Use the existing simulation GPU; wait without stopping other runs.
            state.update(status="waiting_resources", case_index=index)
            save()
            deadline = time.monotonic() + 21600
            while True:
                query = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], text=True)
                free = int(query.splitlines()[int(definition["simulation_gpu"])])
                if free >= 7500:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("GPU resource wait exceeded six hours")
                time.sleep(10)
            check_sources(definition["source_sha256"])
            verify_prepared(record)
            if not health(config)["ready"]:
                raise RuntimeError("Pinned model became unavailable during resource wait")
            env = dict(os.environ, **record["environment"], CUDA_VISIBLE_DEVICES=definition["simulation_gpu"])
            output = Path(record["argv"][2])
            attempt = dict(case_id=record["plan"]["case_id"], output=str(output), status="running", started_at=time.time())
            state["cases"].append(attempt)
            with Path(str(output) + ".launch.log").open("w") as log:
                child = subprocess.Popen(record["argv"], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                         stdout=log, stderr=subprocess.STDOUT)
                attempt["pid"] = child.pid
                state["status"] = "running_case"
                save()
                while child.poll() is None:
                    observations = sorted((output / "controller/robot").glob("observation_*/observation.json"))
                    if observations:
                        attempt["last_step"] = json.loads(observations[-1].read_text())["step_id"]
                    save()
                    time.sleep(10)
            attempt.update(returncode=child.returncode, finished_at=time.time(), status="finished")
            summary_file = output / "controller/summary.json"
            summary = json.loads(summary_file.read_text()) if summary_file.exists() else None
            attempt["summary"] = summary
            native = (summary or {}).get("native_outcome") or {}
            if child.returncode or not (native.get("complete") and native.get("valid_for_success_rate")):
                state.update(status="halted", reason="case_incomplete_or_infrastructure_error")
                return
            if native.get("evaluation_case") != record["plan"]["evaluation_identity"]:
                raise ValueError("Final native outcome identity does not match queued case")
            save()
        state["status"] = "complete"
    except (Exception, KeyboardInterrupt) as error:
        state.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "error", error=repr(error))
        if child is not None and child.poll() is None:
            child.terminate()  # owned shell trap also terminates its controller/backend
    finally:
        save()


if __name__ == "__main__":
    main()

"""Serial, resumable execution of never-attempted published A-line cases."""

import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

from agent_action.a_panel import prepare
from agent_action.service import health, matches_process, process_identity, write_state

ROOT = Path(__file__).resolve().parents[1]


def round_robin(cases, tasks):
    groups = [[case for case in cases if case['task'] == task] for task in tasks]
    return [group[index] for index in range(max(map(len, groups), default=0)) for group in groups if index < len(group)]


def never_attempted(report, task_order):
    return round_robin([case for case in report['cases'] if case['state'] == 'pending' and not case['attempts']], task_order)


def resources_ready(gpu, minimum_mib, ports):
    result = subprocess.run(['nvidia-smi', '-i', str(gpu), '--query-gpu=memory.free', '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, check=True, timeout=10)
    free = int(result.stdout.strip())
    if free < minimum_mib:
        return False, dict(free_mib=free, reason='gpu_memory')
    for port in ports:
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(('127.0.0.1', port)) == 0:
                return False, dict(free_mib=free, reason='port_busy', port=port)
    return True, dict(free_mib=free)


def outcome_policy(summary, returncode):
    """Never retry; native failure continues, infrastructure faults halt the queue."""
    if not summary:
        return 'halt_missing_summary'
    if summary.get('status') in ('infrastructure_error', 'simulator_error'):
        return 'halt_infrastructure'
    if returncode and summary.get('status') != 'controller_error':
        return 'halt_launcher_error'
    return 'continue'


def scoped_report(report, tasks, cases_per_task=None):
    ordered = round_robin([case for case in report['cases'] if case['task'] in tasks], tasks)
    allowed = {case['case_id'] for case in ordered[:len(tasks) * cases_per_task]} if cases_per_task else None
    cases = [case for case in report['cases'] if case['task'] in tasks and (allowed is None or case['case_id'] in allowed)]
    return dict(report, cases=cases, planned_cases=len(cases),
        attempted_cases=sum(bool(c['attempts']) for c in cases),
        complete_cases=sum(c['state'] == 'completed' for c in cases),
        pending_cases=sum(c['state'] == 'pending' for c in cases),
        review_cases=sum(c['state'] == 'needs_review' for c in cases),
        successful_cases=sum(c['result'] is not None and c['result']['native_success'] is True for c in cases))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--harness-root', type=Path, default=ROOT)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--codex', type=Path, required=True)
    parser.add_argument('--robodojo', type=Path, required=True)
    parser.add_argument('--runs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--after-run', type=Path)
    parser.add_argument('--gpu', type=int, default=1)
    parser.add_argument('--minimum-free-mib', type=int, default=9000)
    parser.add_argument('--tasks', nargs='+', help='Predeclared subset of the published task order')
    parser.add_argument('--cases-per-task', type=int, default=1, help='Frozen-order pilot cases per selected task')
    args = parser.parse_args()
    root, output, runs = args.harness_root.resolve(), args.output.resolve(), args.runs.resolve()
    output.mkdir(parents=True, exist_ok=True)
    runs.mkdir(parents=True, exist_ok=True)
    panel_path = root / 'configs/a_published_ten_task_panel.json'
    native_path = root / 'configs/a_native_panel60_v1.json'
    panel = json.loads(panel_path.read_text())
    tasks = args.tasks or panel['task_order']
    if len(set(tasks)) != len(tasks) or not set(tasks) <= set(panel['task_order']):
        raise ValueError('Task selection must contain distinct published tasks')
    if not 1 <= args.cases_per_task <= 5:
        raise ValueError('Cases per task must be within 1..5')
    native = json.loads(native_path.read_text())
    config = json.loads((root / 'configs/base_model.json').read_text())
    lock = (runs / '.batch.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(args.gpu), PYTHONPATH=os.pathsep.join(
        [str(root), str(args.reference.resolve()), os.environ.get('PYTHONPATH', '')]),
        ROLLOUT_EVAL_MANIFEST_SHA256=native['panel_sha256'])
    sys.path.insert(0, str(args.reference.resolve()))
    from hybrid_rollout.robodojo.evaluation import read_panel, verify_assets

    state = dict(schema='agent_action.a_batch.v1', host=socket.gethostname(), pid=os.getpid(),
        panel_sha256=panel['panel_sha256'], native_panel_sha256=native['panel_sha256'],
        planned_cases=len(tasks) * args.cases_per_task, planned_tasks=len(tasks), cases_per_task=args.cases_per_task,
        selected_tasks=tasks, frozen_panel_cases=len(panel['cases']),
        harness_root=str(root), reference=str(args.reference.resolve()), runs=str(runs),
        gpu=args.gpu, minimum_free_mib=args.minimum_free_mib,
        order='round_robin_tasks_then_frozen_case_order', automatic_retry=False,
        budget_protocol='frozen_native_horizons', attempted_by_batch=0, finished_by_batch=0,
        current_case=None, current_run=None, after_run=str(args.after_run.resolve()) if args.after_run else None)
    child = None

    def save(status, **fields):
        state.update(status=status, updated_at=dt.datetime.now(dt.timezone.utc).isoformat(), **fields)
        write_state(output / 'state.json', state)

    def report():
        complete = prepare(panel, args.robodojo.resolve(), runs, panel_path, native, native_path)
        write_state(output / 'all-panel-results.json', complete)
        value = scoped_report(complete, tasks, args.cases_per_task)
        write_state(output / 'results.json', value)
        state.update(attempted_cases=value['attempted_cases'], complete_cases=value['complete_cases'],
                     pending_cases=value['pending_cases'], review_cases=value['review_cases'],
                     successful_cases=value['successful_cases'])
        return value

    def interrupted(*_):
        raise KeyboardInterrupt('Stopping owned batch and its current launcher only')
    signal.signal(signal.SIGTERM, interrupted)

    try:
        save('preflight')
        verify_assets(read_panel(native_path), args.robodojo.resolve())
        initial = report()
        selected = never_attempted(initial, tasks)
        write_state(output / 'execution-plan.json', dict(case_ids=[c['case_id'] for c in selected],
            skipped_existing_attempts=[c['case_id'] for c in initial['cases'] if c['attempts']],
            selected_tasks=tasks, panel_sha256=panel['panel_sha256'], source_commit=subprocess.check_output(
                ['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()))
        if args.after_run:
            after = args.after_run.resolve()
            launch = json.loads(after.with_name(after.name + '.launch.json').read_text())
            if launch['host'] != socket.gethostname():
                raise RuntimeError('Cannot monitor another host using local PIDs')
            identity = process_identity(launch['pid'])
            if identity and str(after) not in identity['argv']:
                raise RuntimeError('Prerequisite launcher PID belongs to another process')
            while identity and matches_process(identity):
                progress = json.loads((after / 'controller/progress.json').read_text())
                save('waiting_development_run', after_run_step=progress.get('step_id'), prerequisite_identity=identity)
                time.sleep(15)
            summary = json.loads((after / 'summary.json').read_text())
            adjustment_path = after / 'budget_adjustment.json'
            adjusted = json.loads(adjustment_path.read_text()) if adjustment_path.exists() else {}
            if summary.get('status') in ('infrastructure_error', 'simulator_error'):
                save('halted_development_infrastructure', prerequisite_summary=summary)
                return
            if summary.get('status') == 'controller_error' and adjusted.get('status') != 'stop_sent':
                save('halted_development_controller', prerequisite_summary=summary)
                return
            # Normal native/development termination or documented user budget stop is eligible.
            save('development_run_finished', prerequisite_summary=summary)
        for item in selected:
            current = report()
            case = next(c for c in current['cases'] if c['case_id'] == item['case_id'])
            if case['attempts']:
                continue
            verify_assets(read_panel(native_path), args.robodojo.resolve())
            if not health(config)['ready']:
                save('halted_model_unavailable')
                return
            while True:
                ready, resource = resources_ready(args.gpu, args.minimum_free_mib, [19124, config['bridge_port']])
                if ready:
                    break
                save('waiting_resources', current_case=case['case_id'], resource=resource)
                time.sleep(15)
            # No shell parsing: the case ID and output path are passed as arguments.
            run = runs / f"{case['case_id']}--attempt-001"
            if run.exists() or run.with_name(run.name + '.plan.json').exists():
                save('halted_attempt_collision', current_case=case['case_id'])
                return
            command = ['bash', str(root / 'scripts/run_a_stack_bowls.sh'), '--case-id', case['case_id'],
                '--codex', str(args.codex.resolve()),
                '--reference', str(args.reference.resolve()), '--robodojo', str(args.robodojo.resolve()),
                '--panel', str(panel_path), '--native-panel', str(native_path), '--output', str(run)]
            with run.with_name(run.name + '.launch.log').open('x') as log:
                child = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            write_state(run.with_name(run.name + '.launch.json'), dict(pid=child.pid, host=socket.gethostname(),
                started_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                argv=command, CUDA_VISIBLE_DEVICES=str(args.gpu), batch=str(output)))
            state['attempted_by_batch'] += 1
            while child.poll() is None:
                progress_path = run / 'controller/progress.json'
                try:
                    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
                except json.JSONDecodeError:
                    progress = {}
                save('running', current_case=case['case_id'], current_run=str(run),
                     launcher_pid=child.pid, current_step=progress.get('step_id'), native_horizon=case['native_horizon'])
                time.sleep(5)
            code = child.returncode
            child = None
            summary_path = run / 'summary.json'
            summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
            state['finished_by_batch'] += 1
            report()
            policy = outcome_policy(summary, code)
            if policy != 'continue':
                save(policy, last_returncode=code, last_summary=summary)
                return
            save('case_finished', last_returncode=code, last_summary=summary)
        report()
        save('finished', current_case=None, current_run=None)
    except KeyboardInterrupt as error:
        save('interrupted', error=str(error))
        raise
    except BaseException as error:
        save('halted_error', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        if child and child.poll() is None:
            os.kill(child.pid, signal.SIGTERM)
            child.wait(timeout=90)
        lock.close()


if __name__ == '__main__':
    main()

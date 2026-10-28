"""Read-only acceptance evidence for A-line tool loops, independent of task success."""

import argparse
import datetime
import gzip
import json
from pathlib import Path
import subprocess

import numpy as np


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def audit(run: Path) -> dict:
    controller = run / 'controller'
    history = read(controller / 'history.json', [])
    progress = read(controller / 'progress.json', {})
    summary = read(run / 'summary.json')
    native = read(run / 'sim/evaluation_outcome.json', {})
    result = read(controller / 'result.json', {})
    issues = []
    executed = 0
    end = 0
    verified = 0
    for row in history:
        steps = row['executed_steps']
        if row['start_tick'] != end or row['end_tick'] - row['start_tick'] != steps or steps <= 0:
            issues.append(f"Non-contiguous execution at decision {row['decision']}")
        end = row['end_tick']
        executed += steps
        path = controller / f"execution_{row['decision']:03d}.npz"
        try:
            with np.load(path, allow_pickle=False) as arrays:
                valid = (arrays['actions'].shape == (steps, 14) and arrays['states'].shape == (steps, 14)
                         and np.isfinite(arrays['actions']).all() and np.isfinite(arrays['states']).all())
            if not valid:
                raise ValueError('Invalid action/state arrays')
            verified += 1
        except (OSError, ValueError, KeyError) as error:
            issues.append(f'{path.name}: {error}')
    # Live writers may be between history and progress updates. Do not call that failure.
    consistent = bool(history) and executed == end == progress.get('step_id')
    images = 0
    image_requests = 0
    unreadable_requests = 0
    for path in (run / 'model_requests').glob('*.input.json.gz'):
        try:
            request = json.loads(gzip.decompress(path.read_bytes()))['model_request']
            count = sum(part.get('type') == 'image_url' for message in request.get('messages', [])
                        if isinstance(message.get('content'), list) for part in message['content'])
            images += count
            image_requests += count > 0
        except (OSError, EOFError, ValueError, KeyError):
            unreadable_requests += 1
    observations = []
    for path in (controller / 'observations').glob('*/observation.json'):
        item = read(path, {})
        if item.get('episode_id') == progress.get('episode_id') and item.get('images') and all(Path(i['path']).is_file() for i in item['images']):
            observations.append(item.get('step_id'))
    compactions = 0
    rpc = controller / 'codex_workspace/rpc_out.jsonl'
    if rpc.exists():
        for line in rpc.open():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            compactions += (event.get('method') == 'item/completed' and event.get('params', {}).get('item', {}).get('type') == 'contextCompaction')
    calls = [read(p, {}) for p in (controller / 'codex_workspace').glob('call_*_result.json')]
    rejects = sum(c.get('no_execution') is True for c in calls)
    loop = (len(history) >= 2 and verified == len(history) and consistent and not issues
            and image_requests > 0 and 0 in observations and end in observations)
    normal = (summary is not None and summary.get('status') in ('completed', 'budget_censored')
              and result.get('reason') in ('terminal', 'control_step_budget')
              and result.get('step_id') == end)
    video = dict(status='deferred_until_finalization')
    if summary is not None:
        try:
            probe = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_entries',
                'stream=nb_read_frames,width,height', '-of', 'json', str(run / 'sim/sensors.mp4')],
                capture_output=True, text=True, check=True, timeout=60)
            streams = json.loads(probe.stdout)['streams']
            valid = len(streams) == 1 and int(streams[0]['nb_read_frames']) == end + 1
            video = dict(status='passed' if valid else 'failed', streams=streams)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            video = dict(status='failed', error=str(error))
    usage = read(controller / 'token_usage.json', {})
    cost_saved = isinstance(usage.get('usage', {}).get('total', {}).get('totalTokens'), int)
    accepted = loop and normal and video['status'] == 'passed' and cost_saved
    return dict(schema='agent_action.a_acceptance.v1', checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        run=str(run), snapshot_only=True, status='passed' if accepted else 'incomplete' if summary is None else 'failed',
        tool_loop_verified=bool(loop), normal_termination_verified=bool(normal),
        task_success_required=False, task_result=dict(complete=native.get('complete', False),
        native_success=native.get('native_success') if native.get('complete') else None,
        native_score=native.get('native_score') if native.get('complete') else None),
        execution=dict(decisions=len(history), verified_arrays=verified, control_steps=executed,
                       progress_consistent=consistent, issues=issues),
        images=dict(model_requests_with_images=image_requests, image_parts=images,
                    observations_with_existing_images=len(observations), unreadable_requests=unreadable_requests),
        recoverable_no_execution_rejections=rejects, context_compactions=compactions,
        memory_fidelity='not_automatically_verified', video=video, cost_saved=cost_saved, usage=usage,
        attribution='Task failure alone does not fail chain acceptance; infrastructure and adapter faults require separate review.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run.resolve())
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    print(json.dumps({k: report[k] for k in ('status', 'tool_loop_verified', 'normal_termination_verified', 'task_result')}))


if __name__ == '__main__':
    main()

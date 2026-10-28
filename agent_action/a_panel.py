"""Audit frozen A-line cases and prepare commands without launching simulators."""

import argparse
import hashlib
import json
from pathlib import Path
import shlex

from agent_action.a_line import published_case_plan, validate_native_budget


def prepare(panel: dict, robodojo: Path, runs: Path, panel_path: Path | None = None,
            native_panel: dict | None = None, native_panel_path: Path | None = None) -> dict:
    """Keep interrupted attempts separate and never infer missing native scores."""
    if native_panel is None:
        native_panel = json.loads((Path(__file__).resolve().parents[1] / 'configs/a_native_panel60_v1.json').read_text())
    payload = {k: v for k, v in native_panel.items() if k != 'panel_sha256'}
    if hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                allow_nan=False).encode()).hexdigest() != native_panel['panel_sha256']:
        raise ValueError('Native evaluation panel hash mismatch')
    cases = []
    for case in panel['cases']:
        plan = published_case_plan(panel, case['case_id'])
        validate_native_budget(plan)
        native_cases = [c for c in native_panel['cases'] if c['case_id'] == case['case_id']]
        if len(native_cases) != 1 or native_cases[0]['layout'] != case['layout']:
            raise ValueError('Native panel layout differs from published case')
        native_case = native_cases[0]
        identity = dict(panel_id=native_panel['panel_id'], panel_sha256=native_panel['panel_sha256'],
                        **{k: native_case[k] for k in ('case_id', 'task', 'runtime_task', 'variant', 'eval_seed',
                            'layout_id', 'reset_seed', 'simulator_initial_seed', 'policy_rng_seed')},
                        layout_sha256=native_case['layout']['sha256'])
        for asset in [case['layout'], *case.get('native_support_trajectories', [])]:
            path = robodojo / asset['path']
            if hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
                raise ValueError(f"Frozen asset mismatch: {asset['path']}")
        attempts = []
        for snapshot in sorted(runs.glob('*.plan.json')):
            record = json.loads(snapshot.read_text())
            saved = record.get('plan', {})
            if saved.get('case_id') != case['case_id']:
                continue
            if saved != plan:
                raise ValueError(f'Attempt plan differs from frozen case: {snapshot}')
            run = snapshot.with_name(snapshot.name.removesuffix('.plan.json'))
            summary_path = run / 'summary.json'
            summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
            native_path = run / 'sim/evaluation_outcome.json'
            native = json.loads(native_path.read_text()) if native_path.exists() else {}
            manifest_path = run / 'manifest.json'
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
            identity_verified = (record.get('evaluation_identity') == identity
                                 and manifest.get('evaluation_identity') == identity
                                 and native.get('evaluation_case') == identity)
            valid = (summary is not None and summary.get('status') == 'completed'
                     and identity_verified
                     and native.get('complete') is True
                     and native.get('valid_for_success_rate') is True
                     and isinstance(native.get('native_success'), bool))
            attempts.append(dict(run=str(run), summary_present=summary is not None,
                                 status=summary.get('status') if summary else 'unfinished_or_interrupted',
                                 valid_native_result=valid,
                                 identity_verified=identity_verified,
                                 native_success=native.get('native_success') if valid else None,
                                 native_score=native.get('native_score') if valid else None,
                                 native_control_steps=native.get('native_control_steps'),
                                 task_outcome=summary.get('task_outcome') if summary else None))
        completed = [a for a in attempts if a['valid_native_result']]
        # Multiple complete results need explicit review, never best-of selection.
        if len(completed) > 1:
            raise ValueError(f"Multiple complete attempts require review: {case['case_id']}")
        number = 1
        while True:
            output = runs / f"{case['case_id']}--attempt-{number:03d}"
            if not output.exists() and not output.with_name(output.name + '.plan.json').exists():
                break
            number += 1
        command = ['bash', 'scripts/run_a_stack_bowls.sh', '--case-id', case['case_id'],
                   '--robodojo', str(robodojo), '--output', str(output)]
        if panel_path is not None:
            command.extend(['--panel', str(panel_path)])
        if native_panel_path is not None:
            command.extend(['--native-panel', str(native_panel_path)])
        cases.append(dict(case_id=case['case_id'], task=case['task'], variant=case['variant'],
                          native_horizon=case['native_horizon'], attempts=attempts,
                          state='completed' if completed else 'needs_review' if attempts else 'pending',
                          result=completed[0] if completed else None,
                          prior_direct=dict(complete=case['prior_direct'].get('native_complete'),
                                            success=case['prior_direct'].get('success') if case['prior_direct'].get('native_complete') else None,
                                            score=case['prior_direct'].get('score') if case['prior_direct'].get('native_complete') else None),
                          next_command=None if completed else shlex.join(command)))
    return dict(schema='agent_action.a_panel_readiness.v1', panel_sha256=panel['panel_sha256'],
                native_panel_sha256=native_panel['panel_sha256'],
                launches_processes=False, planned_cases=len(cases),
                attempted_cases=sum(bool(c['attempts']) for c in cases),
                total_attempts=sum(len(c['attempts']) for c in cases),
                complete_cases=sum(c['state'] == 'completed' for c in cases),
                pending_cases=sum(c['state'] == 'pending' for c in cases),
                review_cases=sum(c['state'] == 'needs_review' for c in cases),
                successful_cases=sum(c['result'] is not None and c['result']['native_success'] is True for c in cases),
                cases=cases)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panel', type=Path, default=root / 'configs/a_published_ten_task_panel.json')
    parser.add_argument('--native-panel', type=Path, default=root / 'configs/a_native_panel60_v1.json')
    parser.add_argument('--robodojo', type=Path, required=True)
    parser.add_argument('--runs', type=Path, required=True, help='Directory containing run plans and attempts')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = prepare(json.loads(args.panel.read_text()), args.robodojo.resolve(), args.runs.resolve(), args.panel.resolve(),
                     json.loads(args.native_panel.read_text()), args.native_panel.resolve())
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, ensure_ascii=False))


if __name__ == '__main__':
    main()

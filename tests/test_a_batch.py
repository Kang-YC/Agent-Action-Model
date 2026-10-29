from agent_action.a_batch import never_attempted, outcome_policy, round_robin, scoped_report


def test_round_robin_covers_every_task_before_second_case_without_reordering_within_task():
    cases = [dict(case_id=f'{t}-{i}', task=t) for t in ('a', 'b', 'c') for i in range(5)]
    ordered = round_robin(cases, ['a', 'b', 'c'])
    assert [c['case_id'] for c in ordered[:6]] == ['a-0', 'b-0', 'c-0', 'a-1', 'b-1', 'c-1']
    assert len({c['case_id'] for c in ordered}) == 15


def test_previously_attempted_failed_and_unfinished_cases_are_never_retried():
    report = dict(cases=[
        dict(case_id='failed', task='a', state='completed', attempts=[dict(native_success=False)]),
        dict(case_id='interrupted', task='a', state='needs_review', attempts=[{}]),
        dict(case_id='new', task='b', state='pending', attempts=[]),
    ])
    assert [c['case_id'] for c in never_attempted(report, ['a', 'b'])] == ['new']


def test_native_failure_continues_but_infrastructure_failure_halts():
    assert outcome_policy(dict(status='completed', task_outcome='failure_native'), 0) == 'continue'
    assert outcome_policy(dict(status='controller_error'), 1) == 'halt_controller_error'
    assert outcome_policy(dict(status='simulator_error'), 1) == 'halt_infrastructure'
    assert outcome_policy(dict(status='infrastructure_error'), 1) == 'halt_infrastructure'
    assert outcome_policy(None, 1) == 'halt_missing_summary'


def test_two_task_subset_keeps_five_cases_each_and_excludes_other_tasks():
    cases = [dict(case_id=f'{task}-{i}', task=task, state='pending', attempts=[], result=None)
             for task in ('organize_table', 'classify_objects', 'put_bottles_into_dustbin') for i in range(5)]
    report = dict(cases=cases, planned_cases=15)
    subset = scoped_report(report, ['classify_objects', 'put_bottles_into_dustbin'])
    assert subset['planned_cases'] == subset['pending_cases'] == 10
    assert subset['attempted_cases'] == subset['complete_cases'] == 0
    order = never_attempted(subset, ['classify_objects', 'put_bottles_into_dustbin'])
    assert [c['task'] for c in order[:2]] == ['classify_objects', 'put_bottles_into_dustbin']
    assert len(order) == 10


def test_one_case_per_task_pilot_is_two_predeclared_cases_not_ten():
    cases = [dict(case_id=f'{task}-{i}', task=task, state='pending', attempts=[], result=None)
             for task in ('classify_objects', 'put_bottles_into_dustbin') for i in range(5)]
    tasks = ['classify_objects', 'put_bottles_into_dustbin']
    report = scoped_report(dict(cases=cases), tasks, 1)
    assert report['planned_cases'] == 2
    assert [c['case_id'] for c in never_attempted(report, tasks)] == ['classify_objects-0', 'put_bottles_into_dustbin-0']

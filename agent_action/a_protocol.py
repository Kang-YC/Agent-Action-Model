"""Recorded adaptation of the published policy prompt to a local model endpoint."""

import ast
import hashlib
from pathlib import Path
import subprocess

REFERENCE_COMMIT = '8f3d362b077d8efb77e2a7274d5b2c20e2243846'
RUN_PATH = 'hybrid_rollout/robodojo/skill/run.py'


def align_published_policy(snapshot: Path, reference: Path) -> dict:
    """Change the owned snapshot only; preserve original policy guidance and loop."""
    worker = snapshot / 'hybrid_rollout/luban_direct/worker.py'
    source = worker.read_text()
    start_marker = "        geometry = self.agent_workspace/'context/robot_geometry'\n"
    end_marker = '        self.prompt_sha256 = hashlib.sha256(self.prompt.encode()).hexdigest()\n'
    image_marker = "self.method, self.timeout, self.image_max_edge = 'gpt_only', timeout, 640"
    if source.count(start_marker) != 1 or source.count(end_marker) != 1 or source.count(image_marker) != 1:
        raise ValueError('Unknown local adapter source; refusing an unverified prompt rewrite')
    start, end = source.index(start_marker), source.index(end_marker)
    if end <= start:
        raise ValueError('Invalid local adapter prompt block')
    replacement = (
        "        self.prompt = ((root/'SKILL.md').read_text() + " + repr('\n\n') + " + teacher.read_text() +\n"
        "            " + repr('\n\nAgent working directory: ') + " + str(self.agent_workspace) +\n"
        "            " + repr('\nResolve context/ and workspace.json relative to that directory.\n') + ")\n"
        "        write_json(self.workspace/'tools.json', tool_specs('gpt_only'))\n")
    adapted = (source[:start] + replacement + source[end:]).replace(image_marker,
        "self.method, self.timeout, self.image_max_edge = 'gpt_only', timeout, 480", 1)
    network_override = ("    def _network_continue(self, *args, **kwargs):\n"
        "        raise RuntimeError('Transport failed; automatic continuation disabled for this experiment')\n")
    if adapted.count(network_override) != 1:
        raise ValueError('Unknown local network override; refusing partial reference alignment')
    adapted = adapted.replace(network_override, '', 1)
    ast.parse(adapted)
    original_loop = subprocess.check_output(['git', '-C', str(reference), 'show', f'{REFERENCE_COMMIT}:{RUN_PATH}'])
    if b"CONTROLLER_VERSION = 'recoverable_tool_input_v1'" not in original_loop:
        raise ValueError('Unexpected published controller identity')
    worker.write_text(adapted)
    (snapshot / RUN_PATH).write_bytes(original_loop)
    return dict(protocol='published_reference', reference_commit=REFERENCE_COMMIT,
        image_max_edge=480, added_static_calibration=False, extra_continuation_guidance=False,
        original_same_thread_network_recovery=True,
        controller_version='recoverable_tool_input_v1',
        worker_original_sha256=hashlib.sha256(source.encode()).hexdigest(),
        worker_adapted_sha256=hashlib.sha256(adapted.encode()).hexdigest(),
        controller_sha256=hashlib.sha256(original_loop).hexdigest(),
        remaining_differences=['specified base model and local API adapter', '32768-token model context',
            'provider-specific xhigh reasoning unavailable', 'isolated local Codex tool configuration',
            'model identity text substituted; runtime workspace paths differ', 'RPC idle-wait infrastructure fix'])


def guard_development_progress(snapshot: Path, timeout_seconds=900) -> dict:
    """Bound physical inactivity independently of image/shell/model activity."""
    path = snapshot / RUN_PATH
    source = path.read_text()
    marker = '        while True:\n            remaining = deadline - time.monotonic()'
    if source.count(marker) != 1 or 'stalled_turns = 0 if turn_control_progress else stalled_turns + 1' not in source:
        raise ValueError('Unknown development progress loop; refusing an unchecked patch')
    replacement = f'''        progress_tick = rollout.tick
        progress_deadline = time.monotonic() + {timeout_seconds}
        while True:
            if rollout.tick != progress_tick:
                progress_tick = rollout.tick
                progress_deadline = time.monotonic() + {timeout_seconds}
            if time.monotonic() >= progress_deadline:
                raise RuntimeError('No physical control progress within {timeout_seconds} seconds')
            remaining = min(deadline, progress_deadline) - time.monotonic()'''
    patched = source.replace(marker, replacement)
    ast.parse(patched)
    path.write_text(patched)
    return dict(no_control_progress_seconds=timeout_seconds, max_stalled_turns=12,
                reset_on='acknowledged_control_step',
                original_sha256=hashlib.sha256(source.encode()).hexdigest(),
                patched_sha256=hashlib.sha256(patched.encode()).hexdigest())


def unify_translation_guidance(snapshot: Path) -> dict:
    """Clarify the unchanged norm bound in the owned A snapshot only."""
    from agent_action.robot import CONTRACT

    rule = CONTRACT.translation_rule()
    skill = snapshot / 'hybrid_rollout/robodojo/skill'
    path = skill / 'run.py'
    source = path.read_text()
    marker = "'No pi05 inference, proposals or direct joint-action commands exist.',"
    start = source.index('def rejected_input(')
    end = source.index('\n\ndef ', start + 1)
    rejection = source[start:end]
    if source.count(marker) != 1 or rejection.count('    return packet') != 1:
        raise ValueError('Unknown Direct tool or rejection source; refusing partial guidance update')
    updated = source[:start] + rejection.replace('    return packet',
        '    packet["translation_constraint"] = ' + repr(rule) + '\n    return packet', 1) + source[end:]
    updated = updated.replace(marker, marker[:-1] + ' + ' + repr(' ' + rule) + ',', 1)
    ast.parse(updated)
    files = {path: (source, updated)}
    direct_skill = snapshot / 'hybrid_rollout/robodojo/robodojo-gpt-only-rollout'
    for relative in ('SKILL.md', 'context/eef_control.md'):
        doc = direct_skill / relative
        original = doc.read_text()
        files[doc] = (original, original.rstrip() + '\n\n### Translation limit (shared execution rule)\n\n' + rule + '\n')
    hashes = {}
    for target, (before, after) in files.items():
        target.write_text(after)
        hashes[str(target.relative_to(snapshot))] = dict(
            before_sha256=hashlib.sha256(before.encode()).hexdigest(),
            after_sha256=hashlib.sha256(after.encode()).hexdigest())
    return dict(version='euclidean_translation_guidance_v2', rule=rule,
                changes_acceptance_rule=False, sources=hashes)


def eef_numeric_feedback(arguments, request):
    """Diagnostic only: measure a rejected candidate without changing it."""
    import math

    if not isinstance(arguments, dict) or not isinstance(request, dict):
        return {}
    response = arguments.get('response')
    if not isinstance(response, dict) or response.get('mode') != 'eef':
        return {}
    if response.get('request_id') != request.get('request_id'):
        return {'unavailable': 'candidate does not match current request_id'}
    arms = {}
    for arm in ('left', 'right'):
        values = {}
        for field, size in (('position', 3), ('quaternion_wxyz', 4)):
            try:
                candidate = response['target'][arm][field]
                if len(candidate) != size or any(type(x) not in (int, float) or not math.isfinite(x) for x in candidate):
                    continue
                if field == 'position':
                    current = request['current_eef'][arm]['position']
                    if len(current) != 3 or any(type(x) not in (int, float) or not math.isfinite(x) for x in current):
                        continue
                    distance = math.dist(candidate, current)
                    if math.isfinite(distance):
                        values.update(distance_m=distance, max_distance_m=0.05,
                                      translation_exceeded=distance > 0.05 + 1e-9)
                else:
                    norm = math.hypot(*candidate)
                    if math.isfinite(norm):
                        values.update(quaternion_norm=norm, quaternion_norm_tolerance=1e-4,
                                      quaternion_norm_invalid=abs(norm - 1) > 1e-4)
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        if values:
            arms[arm] = values
    return {'arms': arms, 'diagnostic_only': True,
            'note': 'Measured against current EEF; these metrics are not full action validation. Correct arguments yourself; no target was modified.'}


def add_numeric_rejection_feedback(snapshot: Path) -> dict:
    """Instrument the owned rejection receipt; retain the native validator."""
    import inspect

    path = snapshot / RUN_PATH
    source = path.read_text()
    start = source.index('def rejected_input(')
    end = source.index('\n\ndef ', start + 1)
    rejection = source[start:end]
    if rejection.count('    return packet') != 1 or 'def eef_numeric_feedback(' in source:
        raise ValueError('Unknown rejection source; refusing numerical feedback patch')
    rejection = rejection.replace('    return packet',
        '    packet["eef_numeric_feedback"] = eef_numeric_feedback(arguments, getattr(rollout, "request", None))\n    return packet', 1)
    updated = source[:start] + inspect.getsource(eef_numeric_feedback) + '\n\n' + rejection + source[end:]
    ast.parse(updated)
    path.write_text(updated)
    return dict(version='eef_numeric_rejection_v1', changes_acceptance_rule=False,
                automatic_action_rewriting=False, additional_tool_calls=0,
                before_sha256=hashlib.sha256(source.encode()).hexdigest(),
                after_sha256=hashlib.sha256(updated.encode()).hexdigest())


def response_input_feedback(error, arguments):
    """Disambiguate the native combined type/ID error without coercing input."""
    if str(error) != 'Response must match the current observation request_id':
        return {}
    response = arguments.get('response') if isinstance(arguments, dict) else None
    if not isinstance(response, dict):
        return dict(native_error=str(error), input_error='response_type',
                    error='response must be a JSON object, not a string, array, scalar or null. '
                          'Supply the response object directly; do not JSON-encode it inside a string.')
    return dict(native_error=str(error), input_error='request_id_mismatch')


def clarify_response_rejection(snapshot: Path) -> dict:
    """Only amend rejected receipts in this run's snapshot; validation stays native."""
    import inspect

    path = snapshot / RUN_PATH
    source = path.read_text()
    start = source.index('def rejected_input(')
    end = source.index('\n\ndef ', start + 1)
    rejection = source[start:end]
    if rejection.count('    return packet') != 1 or 'def response_input_feedback(' in source:
        raise ValueError('Unknown rejection source; refusing response feedback patch')
    rejection = rejection.replace('    return packet',
        '    packet.update(response_input_feedback(error, arguments))\n    return packet', 1)
    updated = source[:start] + inspect.getsource(response_input_feedback) + '\n\n' + rejection + source[end:]
    ast.parse(updated)
    path.write_text(updated)
    return dict(version='response_type_feedback_v1', changes_acceptance_rule=False,
                automatic_action_rewriting=False,
                before_sha256=hashlib.sha256(source.encode()).hexdigest(),
                after_sha256=hashlib.sha256(updated.encode()).hexdigest())

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

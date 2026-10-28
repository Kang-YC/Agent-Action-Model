"""Live evaluation observatory: read experiment artifacts without touching runners."""

import argparse
import datetime as dt
from functools import lru_cache
import json
import mimetypes
from pathlib import Path
import re
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Observatory:
    def __init__(self, artifacts, web=ROOT / 'evaluation_web'):
        self.artifacts = Path(artifacts).resolve()
        self.web = Path(web).resolve()
        self.storage = self.artifacts / 'evaluation-dashboard'
        self.lock = threading.Lock()

    def inside(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.artifacts):
            raise ValueError('Run must be inside the experiment artifacts directory')
        return path

    def discover(self):
        registered = read(self.storage / 'registry.json', {})
        paths = list(self.artifacts.iterdir()) if self.artifacts.exists() else []
        for parent in ('a-published-runs', 'b-published-runs'):
            folder = self.artifacts / parent
            if folder.exists():
                paths.extend(folder.iterdir())
        paths.extend(self.artifacts / p for p in registered)
        runs = {}
        for path in paths:
            try:
                path = self.inside(path)
            except ValueError:
                continue
            if not path.is_dir() or not (path / 'controller').is_dir() or not (path / 'sim').is_dir():
                continue
            key = path.relative_to(self.artifacts).as_posix()
            # IDs are stable relative paths, including future nested evaluation folders.
            runs[key] = path
        return runs

    def run(self, key):
        runs = self.discover()
        if key not in runs:
            raise FileNotFoundError('Unknown evaluation run')
        return runs[key]

    def guards(self, run):
        for p in self.artifacts.glob('*followup*/*budget*/state.json'):
            item = read(p, {})
            argv = item.get('launcher_identity', {}).get('argv', [])
            if str(run) in argv:
                return {k: item.get(k) for k in ('requested_cap', 'status', 'observed_step', 'stop_at_first_completed_action_at_or_above')}
        return None

    def media_url(self, key, path, run):
        from urllib.parse import quote
        try:
            path = Path(path).resolve()
            rel = path.relative_to(run.resolve()).as_posix()
        except (ValueError, TypeError):
            return None
        return '/media/' + quote(key, safe='') + '/' + quote(rel, safe='/')

    def observations(self, run):
        folder = run / 'controller'
        paths = list((folder / 'observations').glob('*/observation.json'))
        paths.extend((folder / 'robot').glob('observation_*/observation.json'))
        return sorted(paths, key=lambda p: p.parent.name)

    def summary(self, key, run):
        c = run / 'controller'
        manifest = read(run / 'manifest.json', {}) or read(c / 'manifest.json', {})
        launch = read(run.with_name(run.name + '.launch.json'), {})
        plan = read(run.with_name(run.name + '.plan.json'), {}).get('plan', {})
        native = read(run / 'sim/evaluation_outcome.json', {})
        summary = read(run / 'summary.json') or read(c / 'summary.json')
        progress = read(c / 'progress.json', {})
        if not progress and summary:
            progress = summary.get('last_observation', {})
        obs_paths = self.observations(run)
        latest = read(obs_paths[-1], {}) if obs_paths else {}
        steps = progress.get('step_id', latest.get('step_id', native.get('native_control_steps', 0)))
        args = manifest.get('arguments', {})
        horizon = native.get('native_step_limit') or latest.get('max_episode_steps') or plan.get('native_control_horizon') or 800
        budget = plan.get('max_control_steps') or manifest.get('max_control_steps') or args.get('max_control_steps') or horizon
        guard = self.guards(run)
        if guard:
            budget = guard['requested_cap']
        alive = False
        if launch.get('host') == socket.gethostname() and launch.get('pid'):
            try:
                command = Path(f"/proc/{launch['pid']}/cmdline").read_bytes().split(b'\0')
                alive = str(run).encode() in command
            except OSError:
                pass
        if summary:
            raw_status = summary.get('status', 'incomplete')
            state = ('budget' if raw_status == 'budget_censored' else
                     'completed' if raw_status == 'completed' else 'error')
        elif alive:
            raw_status, state = 'running', 'running'
        elif native.get('reason') in ('server_close', 'controller_disconnect'):
            raw_status, state = native.get('reason'), 'incomplete'
        else:
            raw_status, state = 'unverified', 'unknown'
        adjustment = read(run / 'budget_adjustment.json')
        if adjustment and adjustment.get('status') == 'stop_sent' and not alive:
            raw_status, state = 'user_development_budget_stop', 'budget'
        usage = read(c / 'token_usage.json', {}).get('usage', {}).get('total', {})
        tokens = usage.get('totalTokens') or (summary or {}).get('total_tokens') or 0
        model_info = manifest.get('model', {})
        model = (manifest.get('inference_config', {}).get('served_model_name') or
                 (model_info.get('served_model_name') if isinstance(model_info, dict) else model_info) or
                 manifest.get('served_model_name') or '未记录')
        line = 'B' if key.startswith('b-') or '/b-' in key else 'A'
        registry = read(self.storage / 'registry.json', {}).get(key, {})
        line = registry.get('line', line)
        task = plan.get('task') or manifest.get('task') or args.get('task') or latest.get('task') or '未记录'
        images = []
        for item in latest.get('images', []):
            url = self.media_url(key, item.get('path'), run)
            if url:
                images.append(dict(camera=item.get('camera', 'camera'), url=url))
        valid = native.get('complete') is True and native.get('valid_for_success_rate') is True
        history = read(c / 'history.json', [])
        actions = list((c / 'robot').glob('action_*.json'))
        loop_observed = (len(history) >= 2 and history[0].get('start_tick') == 0
                         and all(a.get('end_tick') == b.get('start_tick') for a, b in zip(history, history[1:]))
                         and history[-1].get('end_tick') == steps
                         and all((c / f"execution_{a['decision']:03d}.npz").exists() for a in history))
        updated = max([p.stat().st_mtime for p in (c / 'progress.json', c / 'token_usage.json', c / 'summary.json', run / 'summary.json') if p.exists()] or [run.stat().st_mtime])
        return dict(id=key, name=registry.get('name') or key, line=line, task=task,
                    harness=registry.get('harness') or ('Codex Direct' if line == 'A' else 'mini-swe-agent'),
                    model=model, status=state, raw_status=raw_status, steps=steps, budget=budget,
                    native_horizon=horizon, original_budget=plan.get('max_control_steps') or args.get('max_control_steps') or horizon,
                    budget_guard=guard, decisions=len(history) or len(actions), tokens=tokens,
                    tool_loop_observed=loop_observed,
                    started_at=launch.get('started_at_utc') or dt.datetime.fromtimestamp(run.stat().st_mtime, dt.timezone.utc).isoformat(),
                    updated_at=dt.datetime.fromtimestamp(updated, dt.timezone.utc).isoformat(),
                    native_complete=native.get('complete', False), valid_score=valid,
                    native_success=native.get('native_success') if valid else None,
                    native_score=native.get('native_score') if valid else None,
                    case_id=plan.get('case_id'), scope='published' if plan.get('case_id') else 'development',
                    images=images, notes=read(self.storage / 'notes.json', {}).get(key, ''),
                    error=(summary or {}).get('error'), host=launch.get('host'),
                    relative_path=run.relative_to(self.artifacts).as_posix())

    def index(self):
        errors, rows = [], []
        for key, run in self.discover().items():
            try:
                rows.append(self.summary(key, run))
            except (OSError, ValueError, TypeError, KeyError) as error:
                errors.append(dict(id=key, error=str(error)))
        rows.sort(key=lambda r: (r['status'] == 'running', r['started_at']), reverse=True)
        return dict(schema='agent_action.evaluation_observatory.v1', updated_at=stamp(), mode='live',
                    refresh_seconds=15, host=socket.gethostname(), records=rows, read_errors=errors)

    def detail(self, key):
        run = self.run(key)
        c = run / 'controller'
        history = read(c / 'history.json', [])
        calls = []
        for row in history:
            response = row.get('response', {})
            calls.append(dict(id=f"action-{row['decision']}", tool='robodojo_act', status='executed',
                step_start=row.get('start_tick'), step_end=row.get('end_tick'),
                requested_steps=response.get('steps'), executed_steps=row.get('executed_steps'),
                reason=response.get('reason', ''), arguments=response,
                observation=f"observations/{row['decision'] + 1:03d}/observation.json"))
        for path in sorted((c / 'codex_workspace').glob('call_*_result.json')):
            result = read(path, {})
            if result.get('no_execution'):
                request = read(path.with_name(path.name.replace('_result', '_request')), {})
                calls.append(dict(id=path.stem, tool='robodojo_act', status='rejected',
                    step_start=result.get('step_id'), step_end=result.get('step_id'),
                    requested_steps=request.get('arguments', {}).get('response', {}).get('steps'),
                    executed_steps=0, reason=result.get('error', ''), arguments=request))
        for path in sorted((c / 'robot').glob('action_*.json')):
            action = read(path, {})
            calls.append(dict(id=path.stem, tool='move_to', status='executed' if action.get('status') == 'acknowledged' else 'uncertain',
                step_start=action.get('start_step'), step_end=action.get('end_step'),
                requested_steps=action.get('requested_steps'),
                executed_steps=(action.get('end_step', 0) - action.get('start_step', 0)) if action.get('end_step') is not None else None,
                reason='双臂 EEF 控制', arguments=dict(targets=action.get('targets'), requested_steps=action.get('requested_steps'))))
        calls.sort(key=lambda x: (x.get('step_start') or 0, x['id']))
        observations = {}
        for path in self.observations(run):
            observation = read(path, {})
            step = observation.get('step_id')
            if step is None:
                continue
            images = []
            for image in observation.get('images', []):
                source = image.get('path')
                url = self.media_url(key, source, run)
                if url and Path(source).is_file():
                    images.append(dict(camera=image.get('camera', 'camera'), url=url))
            observations[step] = dict(step_id=step, images=images, current_eef=observation.get('current_eef', {}))
        for call in calls:
            arguments = call['arguments']
            response = arguments.get('arguments', {}).get('response', arguments)
            call['targets'] = response.get('target') or response.get('targets') or {}
            call['observations'] = dict(before=observations.get(call['step_start']),
                after=observations.get(call['step_end']) if call['status'] == 'executed' else None)
        events = []
        log = run / 'logs/controller.log'
        if log.exists():
            for line in log.open(errors='replace'):
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get('event') == 'agent_activity' and event.get('phase') == 'completed':
                    events.append(dict(type=event.get('item_type'), step=event.get('step_id'),
                        text=(event.get('text') or event.get('command') or '')[:16000],
                        status=event.get('status'), exit_code=event.get('exit_code')))
        if not events:
            trajectory = read(c / 'trajectory.json', {})
            for message in trajectory.get('messages', []):
                content = message.get('content', '')
                if isinstance(content, str) and message.get('role') in ('assistant', 'tool'):
                    events.append(dict(type=message['role'], step=None, text=content[:16000]))
        row = self.summary(key, run)
        videos = []
        debug_manifest = read(c / 'debug_video/manifest.json', {})
        for path in (run / 'sim/sensors.mp4', c / 'debug_video/debug_rollout.mp4'):
            if not path.exists():
                continue
            available = video_readable(str(path), path.stat().st_size, path.stat().st_mtime_ns)
            videos.append(dict(name='三相机录屏' if path.name == 'sensors.mp4' else 'Agent 调试录像',
                               available=available, url=self.media_url(key, path, run) if available else None,
                               state='ready' if available else 'writing', bytes=path.stat().st_size,
                               sync_available=(path.name == 'sensors.mp4' or
                                   (debug_manifest.get('frame_mapping') == 'initial frame 0; frame t>0 shows action t-1 ACK'
                                    and debug_manifest.get('reading_pause_frames') == 0
                                    and debug_manifest.get('playback_speed') == 1))))
        control_dt = read(run / 'sim/summary.json', {}).get('control_dt') or read(c / 'run.json', {}).get('control_dt') or 0.04
        row.update(calls=calls, events=events, videos=videos, control_dt=control_dt,
                   notes=read(self.storage / 'notes.json', {}).get(key, ''))
        return row

    def write(self, filename, key, value):
        with self.lock:
            self.storage.mkdir(parents=True, exist_ok=True)
            path = self.storage / filename
            data = read(path, {})
            data[key] = value
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            temporary.replace(path)


@lru_cache(maxsize=64)
def video_readable(path, size, modified):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'json', path],
                                capture_output=True, text=True, timeout=8)
        return result.returncode == 0 and any(s.get('codec_type') == 'video' for s in json.loads(result.stdout).get('streams', []))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if args and str(args[1] if len(args) > 1 else '').startswith('5'):
                super().log_message(fmt, *args)

        def json(self, value, code=200):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                path = urlsplit(self.path).path
                if path == '/api/records':
                    return self.json(app.index())
                if path.startswith('/api/run/'):
                    return self.json(app.detail(unquote(path[len('/api/run/'):])) )
                if path.startswith('/media/'):
                    parts = path[len('/media/'):].split('/', 1)
                    if len(parts) != 2:
                        raise FileNotFoundError()
                    run = app.run(unquote(parts[0]))
                    target = (run / unquote(parts[1])).resolve()
                    if not target.is_relative_to(run.resolve()) or target.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.mp4'):
                        raise ValueError('Unsupported media path')
                    return self.file(target)
                name = 'index.html' if path == '/' else unquote(path[1:])
                target = (app.web / name).resolve()
                if not target.is_relative_to(app.web) or target.suffix not in ('.html', '.js', '.css', '.svg'):
                    raise FileNotFoundError()
                return self.file(target)
            except FileNotFoundError:
                self.json(dict(error='Not found'), 404)
            except ValueError as error:
                self.json(dict(error=str(error)), 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as error:
                self.json(dict(error=str(error)), 500)

        def file(self, path):
            if not path.is_file():
                raise FileNotFoundError()
            size = path.stat().st_size
            start, end, code = 0, size - 1, 200
            requested = self.headers.get('Range')
            if requested:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
                if not match or not size:
                    return self.range_error(size)
                left, right = match.groups()
                if not left and not right:
                    return self.range_error(size)
                if not left:
                    length = int(right)
                    if length <= 0: return self.range_error(size)
                    start = max(0, size - length)
                else:
                    start = int(left)
                    if right: end = min(int(right), size - 1)
                if start >= size or end < start:
                    return self.range_error(size)
                code = 206
            self.send_response(code)
            mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith('text/') else ''))
            self.send_header('Content-Length', str(end - start + 1))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if code == 206: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            with path.open('rb') as stream:
                stream.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = stream.read(min(256 * 1024, remaining))
                    if not chunk: break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def range_error(self, size):
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_POST(self):
            try:
                origin = self.headers.get('Origin')
                if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                    return self.json(dict(error='Cross-origin write refused'), 403)
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 32768:
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(length))
                path = urlsplit(self.path).path
                if path.startswith('/api/notes/'):
                    key = unquote(path[len('/api/notes/'):])
                    app.run(key)
                    note = body.get('notes', '')
                    if not isinstance(note, str) or len(note) > 16000:
                        raise ValueError('Note must be text, at most 16000 characters')
                    app.write('notes.json', key, note)
                    return self.json(dict(saved=True))
                if path == '/api/register':
                    run = app.inside(app.artifacts / body['path'])
                    if not (run / 'controller').is_dir() or not (run / 'sim').is_dir():
                        raise ValueError('Expected an existing run with controller/ and sim/')
                    key = run.relative_to(app.artifacts).as_posix()
                    metadata = {k: str(body.get(k, ''))[:200] for k in ('name', 'line', 'harness') if body.get(k)}
                    if metadata.get('line') not in (None, 'A', 'B'):
                        raise ValueError('Line must be A or B')
                    app.write('registry.json', key, metadata)
                    return self.json(dict(saved=True, id=key))
                self.json(dict(error='Not found'), 404)
            except (ValueError, KeyError, FileNotFoundError) as error:
                self.json(dict(error=str(error)), 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, default=ROOT / 'artifacts')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=19340)
    args = parser.parse_args()
    app = Observatory(args.artifacts)
    server = ThreadingHTTPServer((args.host, args.port), handler_for(app))
    print(json.dumps(dict(event='ready', url=f'http://{args.host}:{args.port}', artifacts=str(app.artifacts))), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()

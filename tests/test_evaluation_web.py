import json
from pathlib import Path
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from agent_action.evaluation_web import Observatory, handler_for


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def app(tmp_path):
    artifacts = tmp_path / 'artifacts'
    run = artifacts / 'a-test'
    c = run / 'controller'
    (run / 'sim').mkdir(parents=True)
    image = c / 'observations/001/cam_high.png'
    image.parent.mkdir(parents=True)
    image.write_bytes(b'fixture image')
    write(c / 'progress.json', dict(step_id=3, episode_id='one'))
    write(c / 'observations/001/observation.json', dict(step_id=3, images=[dict(camera='cam_high', path=str(image))]))
    write(c / 'token_usage.json', dict(usage=dict(total=dict(totalTokens=1000))))
    write(c / 'history.json', [dict(decision=0, start_tick=0, end_tick=3, executed_steps=3,
        response=dict(steps=3, reason='move', target={}))])
    write(run / 'sim/evaluation_outcome.json', dict(complete=False, valid_for_success_rate=False, native_success=False, native_score=0))
    web = tmp_path / 'web'
    web.mkdir()
    (web / 'index.html').write_text('<h1>Observatory</h1>')
    return Observatory(artifacts, web)


@pytest.fixture
def server(app):
    http = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(app))
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    yield f'http://127.0.0.1:{http.server_address[1]}'
    http.shutdown()
    http.server_close()
    worker.join(3)


def test_incomplete_native_scores_stay_missing_and_tool_execution_is_visible(app):
    row = app.index()['records'][0]
    assert row['steps'] == 3
    assert row['tokens'] == 1000
    assert row['native_success'] is row['native_score'] is None
    assert not row['valid_score']
    detail = app.detail('a-test')
    assert detail['calls'][0]['executed_steps'] == 3
    assert detail['calls'][0]['status'] == 'executed'
    assert detail['images'][0]['url'].startswith('/media/a-test/')


def test_real_http_range_seek_and_traversal_boundaries(app, server, tmp_path):
    run = app.run('a-test')
    (run / 'sim/sensors.mp4').write_bytes(b'0123456789')
    request = urllib.request.Request(server + '/media/a-test/sim/sensors.mp4', headers={'Range':'bytes=2-5'})
    with urllib.request.urlopen(request) as response:
        assert response.status == 206
        assert response.read() == b'2345'
        assert response.headers['Content-Range'] == 'bytes 2-5/10'
    request = urllib.request.Request(server + '/media/a-test/sim/sensors.mp4', headers={'Range':'bytes=-3'})
    with urllib.request.urlopen(request) as response:
        assert response.read() == b'789'
    request = urllib.request.Request(server + '/media/a-test/sim/sensors.mp4', headers={'Range':'bytes=20-'})
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 416
    secret = tmp_path / 'secret.png'
    secret.write_text('private')
    (run / 'sim/link.png').symlink_to(secret)
    for url in ('/media/a-test/../../secret.png', '/media/a-test/sim/link.png', '/media/a-test/controller/history.json'):
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(server + url)
        assert error.value.code == 400


def test_notes_persist_and_cross_origin_writes_are_refused(app, server):
    request = urllib.request.Request(server + '/api/notes/a-test', data=json.dumps(dict(notes='抓取尚待核验')).encode(),
        headers={'Content-Type':'application/json'}, method='POST')
    with urllib.request.urlopen(request) as response:
        assert json.load(response)['saved']
    assert app.detail('a-test')['notes'] == '抓取尚待核验'
    request = urllib.request.Request(server + '/api/notes/a-test', data=b'{"notes":"bad"}',
        headers={'Origin':'https://other.example'}, method='POST')
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 403
    assert app.detail('a-test')['notes'] == '抓取尚待核验'


def test_nested_run_registration_and_registration_path_limits(app, server, tmp_path):
    nested = app.artifacts / 'future/experiment'
    (nested / 'sim').mkdir(parents=True)
    (nested / 'controller').mkdir()
    body = dict(path='future/experiment', name='未来评测', line='B', harness='mini-swe-agent')
    request = urllib.request.Request(server + '/api/register', data=json.dumps(body).encode(), method='POST')
    with urllib.request.urlopen(request) as response:
        assert json.load(response)['id'] == 'future/experiment'
    assert app.summary('future/experiment', nested)['name'] == '未来评测'
    body['path'] = str(tmp_path)
    request = urllib.request.Request(server + '/api/register', data=json.dumps(body).encode(), method='POST')
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 400


def test_call_images_join_by_exact_step_and_rejections_have_no_after_image(app):
    run = app.run('a-test')
    c = run / 'controller'
    target = dict(left=dict(position=[0.1, -0.2, 0.9], quaternion_wxyz=[1, 0, 0, 0], gripper_closed=True),
                  right=dict(position=[0.3, -0.1, 0.8], quaternion_wxyz=[1, 0, 0, 0], gripper_closed=False))
    history = json.loads((c / 'history.json').read_text())
    history[0]['response']['target'] = target
    write(c / 'history.json', history)
    for name, step in [('000', 0), ('002', 99)]:
        image = c / f'observations/{name}/cam_high.png'
        image.parent.mkdir(parents=True)
        image.write_bytes(b'image')
        write(image.with_name('observation.json'), dict(step_id=step, images=[dict(camera='cam_high', path=str(image))]))
    write(c / 'codex_workspace/call_0001_request.json', dict(arguments=dict(response=dict(target=target, steps=5))))
    write(c / 'codex_workspace/call_0001_result.json', dict(no_execution=True, step_id=3, error='Invalid input'))
    detail = app.detail('a-test')
    executed = next(x for x in detail['calls'] if x['status'] == 'executed')
    rejected = next(x for x in detail['calls'] if x['status'] == 'rejected')
    assert executed['targets'] == target
    assert executed['observations']['before']['step_id'] == 0
    assert executed['observations']['after']['step_id'] == 3
    assert '/001/' in executed['observations']['after']['images'][0]['url']
    assert rejected['targets'] == target
    assert rejected['requested_steps'] == 5
    assert rejected['observations']['before']['step_id'] == 3
    assert rejected['observations']['after'] is None
    (c / 'observations/001/observation.json').unlink()
    executed = next(x for x in app.detail('a-test')['calls'] if x['status'] == 'executed')
    assert executed['observations']['after'] is None  # Never substitute step 99's latest image.


def test_move_to_coordinates_and_before_after_cameras_are_exposed(app):
    run = app.artifacts / 'b-test'
    (run / 'sim').mkdir(parents=True)
    c = run / 'controller'
    target = dict(left=dict(position=[-0.2, -0.3, 0.9], quaternion_wxyz=[1, 0, 0, 0], gripper_closed=True))
    write(c / 'robot/action_0001.json', dict(start_step=0, end_step=5, requested_steps=5, status='acknowledged', targets=target))
    for step in (0, 5):
        images = []
        for camera in ('cam_high', 'cam_left_wrist', 'cam_right_wrist'):
            image = c / f'robot/observation_{step:04d}/{camera}.png'
            image.parent.mkdir(parents=True, exist_ok=True)
            image.write_bytes(b'image')
            images.append(dict(camera=camera, path=str(image)))
        write(image.with_name('observation.json'), dict(step_id=step, images=images))
    call = app.detail('b-test')['calls'][0]
    assert call['tool'] == 'move_to'
    assert call['targets']['left']['position'] == [-0.2, -0.3, 0.9]
    assert call['observations']['before']['step_id'] == 0
    assert call['observations']['after']['step_id'] == 5
    assert len(call['observations']['after']['images']) == 3

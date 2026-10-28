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

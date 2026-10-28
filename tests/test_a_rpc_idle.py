import importlib.util
from pathlib import Path
import socket
from types import SimpleNamespace
import threading
import time

import pytest

from agent_action.direct import patch_rpc_idle_wait


def test_unrecognized_rpc_is_not_silently_patched(tmp_path):
    source = tmp_path / 'rpc.py'
    source.write_text('unrecognized source')
    with pytest.raises(ValueError, match='Unexpected reference RPC'):
        patch_rpc_idle_wait(source)
    assert source.read_text() == 'unrecognized source'


@pytest.mark.parametrize('partial_packet', [False, True])
def test_real_socket_waits_for_thinking_but_bounds_partial_packet(tmp_path, monkeypatch, partial_packet):
    reference = Path(__file__).resolve().parents[2] / 'GPT-as-Policy'
    source = reference / 'hybrid_rollout/robodojo/robodojo_server/rpc.py'
    if not source.exists():
        pytest.skip('Reference checkout required for real RPC integration')
    monkeypatch.syspath_prepend(str(reference))
    patched = tmp_path / 'rpc.py'
    patched.write_text(source.read_text())
    record = patch_rpc_idle_wait(patched)
    assert record['partial_packet_timeout_seconds'] == 900
    assert record['original_sha256'] != record['patched_sha256']
    spec = importlib.util.spec_from_file_location('hybrid_rollout.robodojo.robodojo_server.test_rpc', patched)
    rpc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rpc)
    ready = threading.Event()
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]

    class Connection:
        def __init__(self, sock): self.sock = sock
        def __enter__(self): return self
        def __exit__(self, *args): self.sock.close()
        def __getattr__(self, name): return getattr(self.sock, name)
        def settimeout(self, value):
            assert value == 900
            self.sock.settimeout(0.05)

    class Listener:
        def __enter__(self): return self
        def __exit__(self, *args): listener.close()
        def __getattr__(self, name): return getattr(listener, name)
        def bind(self, address):
            assert address == listener.getsockname()
        def listen(self, count):
            listener.listen(count)
            ready.set()
        def accept(self):
            sock, address = listener.accept()
            return Connection(sock), address

    rpc.socket = SimpleNamespace(socket=lambda *args: Listener(), AF_INET=socket.AF_INET,
        SOCK_STREAM=socket.SOCK_STREAM, SOL_SOCKET=socket.SOL_SOCKET, SO_REUSEADDR=socket.SO_REUSEADDR,
        IPPROTO_TCP=socket.IPPROTO_TCP, TCP_NODELAY=socket.TCP_NODELAY)

    class Session:
        metadata = {}
        terminated = truncated = False
        def __init__(self): self.reasons = []
        def dispatch(self, operation, arguments): return dict(operation=operation)
        def _write_summary(self, reason): self.reasons.append(reason)

    session = Session()
    errors = []
    def serve():
        try: rpc.serve(session, port)
        except BaseException as error: errors.append(error)
    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    assert ready.wait(3), errors
    with socket.create_connection(('127.0.0.1', port), timeout=3) as client:
        try:
            # More than twice the accelerated packet timeout without any request.
            time.sleep(0.15)
            assert worker.is_alive()
            if partial_packet:
                client.sendall(b'\x00')
                worker.join(3)
                assert not worker.is_alive()
            else:
                rpc.send_packet(client, dict(version=rpc.VERSION, request_id='test', op='metadata'))
                assert rpc.receive_packet(client)['result'] == dict(operation='metadata')
        finally:
            client.shutdown(socket.SHUT_RDWR)
    worker.join(3)
    assert not worker.is_alive()
    assert not errors
    assert session.reasons == ['controller_disconnect']

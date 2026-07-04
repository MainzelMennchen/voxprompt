"""Tests für den LLM-Server-Lifecycle-Manager (Server-Start/Stop)."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from voxprompt.server import LLMServerManager, build_command


def test_build_command_ersetzt_host_und_port() -> None:
    cmd = build_command(
        ["mlx_lm.server", "--host", "{host}", "--port", "{port}"],
        "http://127.0.0.1:8080/v1",
    )
    assert cmd == ["mlx_lm.server", "--host", "127.0.0.1", "--port", "8080"]


@pytest.fixture
def stub_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"data": []}')

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/v1"
    srv.shutdown()


def test_is_up_true_wenn_server_antwortet(stub_server) -> None:
    mgr = LLMServerManager(stub_server, command=["false"])
    assert mgr.is_up() is True


def test_is_up_false_wenn_nichts_laeuft() -> None:
    # Port, auf dem (sehr wahrscheinlich) nichts läuft
    mgr = LLMServerManager("http://127.0.0.1:59999/v1", command=["false"])
    assert mgr.is_up() is False


def test_ensure_running_uebernimmt_laufenden_server(stub_server) -> None:
    mgr = LLMServerManager(stub_server, command=["false"])
    assert mgr.ensure_running() == "reused"
    assert mgr.owned is False
    # shutdown darf einen fremden Server NICHT anfassen (kein Prozess gestartet)
    mgr.shutdown()  # no-op, kein Fehler


def test_shutdown_ohne_eigenen_prozess_ist_noop() -> None:
    mgr = LLMServerManager("http://127.0.0.1:59999/v1", command=["false"])
    mgr.shutdown()  # darf nicht crashen
    assert mgr.owned is False

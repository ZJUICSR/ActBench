from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import socket
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib_http import HttpResponseLimitError, urlopen  # noqa: E402


@contextmanager
def http_server(respond):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                respond(self)
            except (OSError, ValueError):
                pass

        do_POST = do_GET

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def open_direct(url, *, timeout=2, **kwargs):
    return urlopen(url, timeout=timeout, handlers=(ProxyHandler({}),), **kwargs)


@pytest.mark.parametrize("phase", ["headers", "body", "error_body", "no_headers"])
def test_total_deadline_covers_stalled_and_trickling_responses(phase):
    def respond(handler):
        if phase == "no_headers":
            time.sleep(0.6)
            return
        if phase == "headers":
            data = b"HTTP/1.1 200 OK\r\nX-Slow: " + b"a" * 100
        else:
            handler.send_response(429 if phase == "error_body" else 200)
            handler.send_header("Content-Length", "100")
            handler.end_headers()
            data = b"a" * 100
        for byte in data:
            handler.wfile.write(bytes([byte]))
            handler.wfile.flush()
            time.sleep(0.01)

    with http_server(respond) as url:
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            with open_direct(url, timeout=0.15) as response:
                response.read()
        assert time.monotonic() - start < 0.7


def test_http_error_body_remains_available_after_request_closes():
    def respond(handler):
        handler.send_response(429)
        handler.end_headers()
        handler.wfile.write(b'{"error":"retry later"}')

    with http_server(respond) as url:
        with pytest.raises(HTTPError) as caught:
            with open_direct(url):
                pytest.fail("HTTP 429 must raise")
        assert caught.value.code == 429
        assert caught.value.read() == b'{"error":"retry later"}'


def test_credentials_cannot_follow_cross_origin_redirect():
    received = threading.Event()
    with http_server(lambda handler: received.set()) as target:

        def redirect(handler):
            handler.send_response(302)
            handler.send_header("Location", target + "/capture")
            handler.end_headers()

        with http_server(redirect) as url:
            with pytest.raises(URLError, match="Cross-origin"):
                with open_direct(Request(url, headers={"Authorization": "Bearer test-secret"})):
                    pytest.fail("credentials must stay at their original service")
    assert not received.is_set()


def test_same_origin_redirect_retains_deadline_and_headers():
    seen = []

    def respond(handler):
        seen.append((handler.path, handler.headers.get("Authorization")))
        if handler.path == "/":
            handler.send_response(307)
            handler.send_header("Location", "/resolved")
            handler.end_headers()
        else:
            handler.send_response(200)
            handler.end_headers()
            handler.wfile.write(b"ok")

    with http_server(respond) as url:
        with open_direct(Request(url, headers={"Authorization": "Bearer test-secret"})) as response:
            assert response.read() == b"ok"
    assert seen == [("/", "Bearer test-secret"), ("/resolved", "Bearer test-secret")]


def test_late_connection_cannot_send_post(monkeypatch):
    release = threading.Event()
    connected = threading.Event()
    received = threading.Event()
    original = socket.create_connection

    def delayed_connect(*args, **kwargs):
        release.wait(2)
        try:
            return original(*args, **kwargs)
        finally:
            connected.set()

    with http_server(lambda _handler: received.set()) as url:
        monkeypatch.setattr(socket, "create_connection", delayed_connect)
        try:
            start = time.monotonic()
            with pytest.raises(TimeoutError):
                with open_direct(Request(url, data=b"must not arrive"), timeout=0.15):
                    pytest.fail("late connection must time out")
            assert time.monotonic() - start < 0.7
        finally:
            release.set()
        assert connected.wait(1)
        assert not received.wait(0.1)


def test_truncated_content_length_is_not_success():
    def respond(handler):
        handler.send_response(200)
        handler.send_header("Content-Length", "100")
        handler.end_headers()
        handler.wfile.write(b"{}")

    with http_server(respond) as url:
        with pytest.raises(http.client.IncompleteRead):
            with open_direct(url) as response:
                response.read()


@pytest.mark.parametrize("mode", ["read", "lines", "chunks"])
def test_response_capture_limit(mode):
    def respond(handler):
        handler.send_response(200)
        handler.end_headers()
        handler.wfile.write(b"x\n" * 50)

    with http_server(respond) as url:
        with pytest.raises(HttpResponseLimitError):
            with open_direct(url, max_bytes=20) as response:
                if mode == "read":
                    response.read()
                elif mode == "lines":
                    list(response)
                else:
                    while response.read1(10):
                        pass


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b": heartbeat\n\n",
        b"data: [DONE]\n\n",
        b'data: {"text":"partial"}\n\n',
        b'data: {"object":"message","status":"completed","text":"partial"}\n\n',
        b'data: {"object":"response","status":"completed"}\n',
        b'data: {"object":"response","status":"failed"}\n\n',
        b'data: {"object":"response","status":"cancelled"}\n\n',
        b'data: {"error":"upstream failed"}\n\n',
    ],
)
def test_qwenpaw_never_accepts_empty_incomplete_or_failed_streams(body):
    from benchmark.backends.qwenpaw import QwenPawRequestError, _post_sse_json

    def respond(handler):
        handler.send_response(200)
        handler.end_headers()
        handler.wfile.write(body)

    with http_server(respond) as url:
        with pytest.raises(QwenPawRequestError):
            _post_sse_json(url, timeout_seconds=1, api_key=None, payload={})


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"])
def test_qwenpaw_completed_response_keeps_trailing_usage_and_unicode(newline):
    from benchmark.backends.qwenpaw import _event_usage, _extract_output_text, _post_sse_json

    text = "first\u2028second"
    events = [
        json.dumps({"text": text}, ensure_ascii=False),
        '{"object":"response",\n"status":"completed"}',
        json.dumps({"type": "turn_usage", "usage": {"total_tokens": 7, "call_count": 1}}),
    ]
    body = b"".join(
        b"".join(b"data: " + line.encode() + newline for line in event.split("\n")) + newline
        for event in events
    )

    def respond(handler):
        handler.send_response(200)
        handler.end_headers()
        # Deliberately split CRLF pairs and UTF-8 characters across socket writes.
        for byte in body:
            handler.wfile.write(bytes([byte]))
            handler.wfile.flush()

    with http_server(respond) as url:
        event = _post_sse_json(url, timeout_seconds=2, api_key=None, payload={})
    assert _extract_output_text(event) == text
    assert _event_usage(event)["total_tokens"] == 7


@pytest.mark.parametrize("slow", ["heartbeat", "unterminated_line"])
def test_qwenpaw_trickling_stream_times_out_and_retains_partial_text(slow):
    from benchmark.backends.qwenpaw import QwenPawTimeoutError, _extract_output_text, _post_sse_json

    def respond(handler):
        handler.send_response(200)
        handler.end_headers()
        handler.wfile.write(b'data: {"text":"partial evidence"}\n\n')
        handler.wfile.flush()
        for _ in range(100):
            handler.wfile.write(b": heartbeat\n\n" if slow == "heartbeat" else b"a")
            handler.wfile.flush()
            time.sleep(0.01)

    with http_server(respond) as url:
        start = time.monotonic()
        with pytest.raises(QwenPawTimeoutError) as caught:
            _post_sse_json(url, timeout_seconds=0.15, api_key=None, payload={})
        assert time.monotonic() - start < 0.7
        assert _extract_output_text(caught.value.partial_response) == "partial evidence"

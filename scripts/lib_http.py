"""HTTP reads with one deadline covering connect, headers and response bodies.

urllib's timeout bounds individual socket waits. A peer sending a slow trickle
can otherwise hold a controller beyond its task budget. Connections are opened
separately so a late DNS result cannot send a POST after the caller has timed out.
"""

from __future__ import annotations

from contextlib import contextmanager
import http.client
import io
import math
import socket
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024


class HttpResponseLimitError(ValueError):
    """An HTTP response exceeded its explicit capture limit."""


def _close_socket(connection) -> None:
    if connection is None:
        return
    try:
        connection.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        connection.close()
    except OSError:
        pass


class _Deadline:
    def __init__(self, timeout: float):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("HTTP timeout must be finite and positive")
        self.until = time.monotonic() + timeout
        self._lock = threading.Lock()
        self._connections = []
        self._sockets = []
        self._closed = False
        self.expired = False
        self._timer = threading.Timer(timeout, self.expire)
        self._timer.daemon = True
        self._timer.start()

    def remaining(self) -> float:
        self.check()
        return max(0.001, self.until - time.monotonic())

    def check(self) -> None:
        if self.expired or self._closed or time.monotonic() >= self.until:
            raise TimeoutError("HTTP request deadline exceeded")

    def track(self, connection) -> None:
        with self._lock:
            self._connections.append(connection)

    def bind(self, connection) -> None:
        with self._lock:
            stop = self._closed or self.expired
            if connection is not None and not stop:
                self._sockets.append(connection)
        if stop:
            _close_socket(connection)

    def expire(self) -> None:
        self.expired = True
        self.close()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            sockets = [*self._sockets, *(connection.sock for connection in self._connections)]
        self._timer.cancel()
        for connection in sockets:
            _close_socket(connection)


def _opener(deadline: _Deadline, handlers):
    class Connection:
        def connect(self):
            deadline.check()
            deadline.track(self)
            done = threading.Event()
            errors = []
            connect = super().connect

            def open_transport():
                try:
                    connect()
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    deadline.bind(self.sock)
                    done.set()

            worker = threading.Thread(
                target=open_transport, daemon=True, name="actbench-http-connect"
            )
            worker.start()
            if not done.wait(deadline.remaining()):
                deadline.expire()
            deadline.check()
            if errors:
                raise errors[0]

        def send(self, data):
            deadline.check()
            if self.sock is None:
                self.connect()
            deadline.check()
            return super().send(data)

    class HTTPConnection(Connection, http.client.HTTPConnection):
        pass

    class HTTPSConnection(Connection, http.client.HTTPSConnection):
        pass

    class HTTPHandler(urllib.request.HTTPHandler):
        def http_open(self, request):
            return self.do_open(HTTPConnection, request)

    class HTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, request):
            return self.do_open(HTTPSConnection, request, context=self._context)

    class RedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, message, headers, new_url):
            def origin(url):
                parts = urlsplit(url)
                port = parts.port or (443 if parts.scheme == "https" else 80)
                return parts.scheme, parts.hostname, port

            if origin(request.full_url) != origin(new_url):
                fp.close()
                raise urllib.error.URLError("Cross-origin HTTP redirect refused")
            return super().redirect_request(request, fp, code, message, headers, new_url)

    # Keep urllib's proxy and TLS verification. Redirects stay on the same origin
    # so API/admin credentials cannot be forwarded to another service. Each request
    # owns its opener; never mutate the process-wide default opener.
    return urllib.request.build_opener(*handlers, HTTPHandler(), HTTPSHandler(), RedirectHandler())


class _Response:
    def __init__(self, response, deadline: _Deadline, limit: int):
        self._response = response
        self._deadline = deadline
        self._remaining = limit

    def __getattr__(self, name):
        return getattr(self._response, name)

    def _read(self, method, amount):
        self._deadline.check()
        data = method(amount)
        self._deadline.check()
        self._remaining -= len(data)
        if self._remaining < 0:
            raise HttpResponseLimitError("HTTP response exceeds capture limit")
        return data

    def read(self, amount=-1):
        size = min(amount, self._remaining + 1) if amount >= 0 else self._remaining + 1
        data = self._read(self._response.read, size)
        if len(data) < size and getattr(self._response, "length", 0):
            raise http.client.IncompleteRead(data, self._response.length)
        return data

    def read1(self, amount=-1):
        size = min(amount, self._remaining + 1) if amount >= 0 else self._remaining + 1
        data = self._read(self._response.read1, size)
        if not data and getattr(self._response, "length", 0):
            raise http.client.IncompleteRead(data, self._response.length)
        return data

    def readline(self, amount=-1):
        limit = min(MAX_LINE_BYTES, self._remaining)
        size = min(amount, limit + 1) if amount >= 0 else limit + 1
        data = self._read(self._response.readline, size)
        if not data and getattr(self._response, "length", 0):
            raise http.client.IncompleteRead(data, self._response.length)
        if len(data) > MAX_LINE_BYTES:
            raise HttpResponseLimitError("HTTP stream line exceeds capture limit")
        return data

    def __iter__(self):
        while line := self.readline():
            yield line


@contextmanager
def urlopen(request, *, timeout: float, max_bytes: int = MAX_RESPONSE_BYTES, handlers=()):
    """Yield an HTTP response with bounded size and an absolute request deadline."""
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("HTTP capture limit must be a positive integer")
    deadline = _Deadline(timeout)
    response = None
    try:
        try:
            response = _opener(deadline, handlers).open(request, timeout=deadline.remaining())
        except urllib.error.HTTPError as exc:
            # Callers read HTTPError bodies in an outer except block. Buffer
            # them while the same deadline and socket ownership still apply.
            try:
                body = _Response(exc, deadline, max_bytes).read()
            finally:
                exc.close()
            raise urllib.error.HTTPError(
                exc.url, exc.code, exc.msg, exc.headers, io.BytesIO(body)
            ) from None
        deadline.check()
        yield _Response(response, deadline, max_bytes)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        if deadline.expired:
            raise TimeoutError("HTTP request deadline exceeded") from exc
        raise
    finally:
        if response is not None:
            response.close()
        deadline.close()

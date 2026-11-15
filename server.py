#!/usr/bin/env python3
"""Local web UI for the PS4 Tools collection.

Start it with ./ps4-tools.sh (or python3 server.py) and open the printed URL.
The server binds to 127.0.0.1 by default; nothing is exposed to the network
unless you pass --host explicitly.
"""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import socket
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
SHARED_STATIC = ROOT / "static"
sys.path.insert(0, str(ROOT))

from tools import TOOLS, ToolError  # noqa: E402

MAX_BODY = 40 * 1024 * 1024
BY_SLUG = {tool.SLUG: tool for tool in TOOLS}
DEFAULT_PORT = 8765

HUB_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PS4 Tools</title>
<link rel="icon" href="/static/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<header class="topbar">
  <a class="brand" href="/"><img src="/static/icon.svg" alt="" width="26" height="26">PS4 <span>Tools</span></a>
  <span class="muted small">local web UI</span>
</header>
<main class="hub">
  <section class="hero">
    <img class="hero-mark" src="/static/icon.svg" width="76" height="76" alt="">
    <div>
      <h1>PS4 Tools</h1>
      <p class="muted">Small utilities for jailbroken PS4 consoles.</p>
    </div>
  </section>
  <h2 class="section-label">Tools</h2>
  <div class="cards">
{cards}
  </div>
</main>
<footer class="foot">Not affiliated with Sony or PlayStation. Use at your own risk.</footer>
</body>
</html>
"""

CARD = """    <a class="card" href="/{slug}">
      <h2>{title}</h2>
      <p>{summary}</p>
      <span class="go">Open &rarr;</span>
    </a>"""


def hub_html() -> str:
    cards = "\n".join(
        CARD.format(
            slug=html.escape(tool.SLUG),
            title=html.escape(tool.TITLE),
            summary=html.escape(tool.SUMMARY),
        )
        for tool in TOOLS
    )
    return HUB_HTML.format(cards=cards)


def _resolve(base: Path, relative: str) -> Path | None:
    """Map a URL path onto a file inside base, or None if it escapes."""
    relative = unquote(relative)
    if not relative or relative.endswith("/"):
        relative += "index.html"
    try:
        base = base.resolve()
        path = (base / relative).resolve()
    except (OSError, ValueError):
        return None
    if not path.is_relative_to(base) or not path.is_file():
        return None
    return path


class Handler(BaseHTTPRequestHandler):
    server_version = "PS4Tools/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"  {self.address_string()}  {fmt % args}\n")

    # -- responses ---------------------------------------------------------

    def _send(
        self,
        status: HTTPStatus,
        content_type: str,
        body: bytes,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_html(self, markup: str) -> None:
        self._send(HTTPStatus.OK, "text/html; charset=utf-8", markup.encode())

    def _send_file(self, path: Path) -> None:
        content_type, _ = mimetypes.guess_type(path.name)
        self._send(
            HTTPStatus.OK,
            content_type or "application/octet-stream",
            path.read_bytes(),
        )

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        # A rejected request may leave unread body bytes; close the connection.
        self.close_connection = True
        body = json.dumps({"error": message}).encode()
        self._send(status, "application/json; charset=utf-8", body)

    def _not_found(self) -> None:
        self._send(
            HTTPStatus.NOT_FOUND,
            "text/plain; charset=utf-8",
            b"Not found\n",
        )

    # -- routes ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/":
            self._send_html(hub_html())
            return
        if path == "/favicon.ico":
            self._send(HTTPStatus.NO_CONTENT, "image/x-icon", b"")
            return
        if path.startswith("/static/"):
            self._serve_static(SHARED_STATIC, path[len("/static/") :])
            return

        for tool in TOOLS:
            prefix = f"/{tool.SLUG}/static/"
            if path.startswith(prefix):
                self._serve_static(tool.STATIC, path[len(prefix) :])
                return
            if path.rstrip("/") == f"/{tool.SLUG}":
                page = _resolve(tool.STATIC, "index.html")
                if page is None:
                    self._not_found()
                else:
                    self._send_file(page)
                return

        self._not_found()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) != 3 or parts[0] != "api":
            self._not_found()
            return

        tool = BY_SLUG.get(parts[1])
        if tool is None:
            self._not_found()
            return

        try:
            payload = self._read_json()
            content_type, body, headers = tool.handle(parts[2], payload)
        except ToolError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._send_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR, f"Unexpected error: {exc}"
            )
            return

        self._send(HTTPStatus.OK, content_type, body, headers)

    # -- helpers -----------------------------------------------------------

    def _serve_static(self, base: Path, relative: str) -> None:
        path = _resolve(base, relative)
        if path is None:
            self._not_found()
            return
        self._send_file(path)

    def _read_json(self) -> dict:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ToolError("Missing Content-Length")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ToolError("Invalid Content-Length") from exc
        if length <= 0:
            raise ToolError("Empty request body")
        if length > MAX_BODY:
            raise ToolError("Request body is larger than 40 MB")
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ToolError("Request body is not valid JSON") from exc
        if not isinstance(data, dict):
            raise ToolError("Request body must be a JSON object")
        return data


def create_server(host: str, port: int) -> ThreadingHTTPServer:
    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    return Server((host, port), Handler)


def _display_host(host: str) -> str:
    return "127.0.0.1" if host in ("0.0.0.0", "::", "") else host


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local web UI for the PS4 Tools collection.",
    )
    parser.add_argument("--port", type=int, default=None, help=f"default {DEFAULT_PORT}")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="address to bind (default 127.0.0.1; 0.0.0.0 exposes it to your LAN)",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open a browser window"
    )
    args = parser.parse_args(argv)

    if args.port is not None:
        try:
            httpd = create_server(args.host, args.port)
        except OSError as exc:
            print(f"ps4-tools: cannot bind {args.host}:{args.port} ({exc})", file=sys.stderr)
            return 1
        port = args.port
    else:
        httpd = None
        for candidate in range(DEFAULT_PORT, DEFAULT_PORT + 20):
            try:
                httpd = create_server(args.host, candidate)
            except OSError:
                continue
            port = candidate
            break
        if httpd is None:
            print(
                f"ps4-tools: no free port in {DEFAULT_PORT}-{DEFAULT_PORT + 19}",
                file=sys.stderr,
            )
            return 1

    url = f"http://{_display_host(args.host)}:{port}/"

    print()
    print("  PS4 Tools")
    print(f"  \u2192 {url}")
    if args.host not in ("127.0.0.1", "localhost"):
        print("  (reachable from other devices on your network)")
    print("  Ctrl+C to stop")
    print(flush=True)

    if not args.no_browser:
        threading.Timer(0.4, webbrowser.open, args=(url,)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

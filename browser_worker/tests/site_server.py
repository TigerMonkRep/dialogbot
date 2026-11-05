"""A tiny local web server for the static booking-site clones in tests/sites/<engine>/ (no network).

`{{key}}` in an HTML file is replaced with the HTML-escaped query parameter `key`; `{{qs}}` with the url-encoded
query string and `{{hidden}}` with one hidden input per parameter, so a static multi-page flow can carry its state.
"""
from __future__ import annotations

import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

SITES = Path(__file__).parent / "sites"
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript", ".css": "text/css"}


def make_handler(engine: str, hits: list[str], hosts: list[str]):
    root = (SITES / engine).resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        def do_GET(self):  # noqa: N802
            parts = urlsplit(self.path)
            hits.append(parts.path)
            hosts.append((self.headers.get("Host") or "").split(":")[0])
            if parts.path == "/redirect-ip":  # same server, other loopback address: only reachable if the guard fails
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.2:{self.server.server_address[1]}/booking/ydelse.html")
                self.end_headers()
                return
            if parts.path == "/redirect-out":
                self.send_response(302)
                self.send_header("Location", "http://evil.invalid/landing")
                self.end_headers()
                return
            rel = parts.path.lstrip("/") or "index.html"
            f = (root / rel).resolve()
            if root not in f.parents or not f.is_file():
                self.send_error(404)
                return
            params = dict(parse_qsl(parts.query, keep_blank_values=True))
            body = f.read_text(encoding="utf-8") if f.suffix in TYPES else None
            if body is None:
                data = f.read_bytes()
            else:
                esc = {k: html.escape(v) for k, v in params.items()}
                hidden = "".join(f'<input type="hidden" name="{html.escape(k)}" value="{v}">' for k, v in esc.items())
                body = body.replace("{{qs}}", html.escape(urlencode(params))).replace("{{hidden}}", hidden)
                import re
                body = re.sub(r"\{\{(\w+)\}\}", lambda m: esc.get(m.group(1), ""), body)
                data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(f.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):  # noqa: N802
            hits.append("POST " + self.path)
            self.send_error(405)

    return Handler


class Site:
    def __init__(self, engine: str = "onlinebooq"):
        self.hits: list[str] = []
        self.hosts: list[str] = []  # the Host header of every request: proves which address the browser really used
        self.server = ThreadingHTTPServer(("0.0.0.0", 0), make_handler(engine, self.hits, self.hosts))  # noqa: S104
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._t = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> Site:
        self._t.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()

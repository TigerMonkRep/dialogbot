"""HTTP-klient til scanneren: måler svartid, registrerer redirect-kæder og dekomprimerer gzip."""
from __future__ import annotations

import gzip
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass, field
from urllib.parse import urljoin

USER_AGENT = "DialogbotSEOAgent/1.0 (+https://www.dialogbot.dk)"
MAX_BODY = 5 * 1024 * 1024
MAX_REDIRECTS = 6


@dataclass
class Response:
    url: str
    final_url: str
    status: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    elapsed_ms: int = 0
    redirects: list[tuple[str, int]] = field(default_factory=list)  # (url, status) for hvert hop
    error: str | None = None
    transfer_size: int = 0  # bytes på tråden (før dekomprimering)

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 300

    @property
    def text(self) -> str:
        return self.body.decode(_charset(self.headers.get("content-type", "")), errors="replace")

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()


def _charset(content_type: str) -> str:
    for part in content_type.split(";")[1:]:
        k, _, v = part.strip().partition("=")
        if k.lower() == "charset" and v:
            return v.strip("\"' ")
    return "utf-8"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401 - urllib-hook
        return None


class Fetcher:
    """Henter URL'er uden at følge redirects automatisk, så kæden kan vurderes."""

    def __init__(self, timeout: float = 20.0, user_agent: str = USER_AGENT):
        self.timeout = timeout
        self.user_agent = user_agent
        self._opener = urllib.request.build_opener(_NoRedirect)

    def get(self, url: str, *, follow: bool = True, method: str = "GET", accept: str = "*/*") -> Response:
        redirects: list[tuple[str, int]] = []
        current = url
        started = time.monotonic()
        for _ in range(MAX_REDIRECTS + 1):
            resp = self._once(current, method, accept)
            if resp.error or not follow or resp.status not in (301, 302, 303, 307, 308):
                resp.url, resp.redirects = url, redirects
                resp.elapsed_ms = int((time.monotonic() - started) * 1000) if redirects else resp.elapsed_ms
                return resp
            target = resp.headers.get("location")
            if not target:
                resp.url, resp.redirects = url, redirects
                return resp
            redirects.append((current, resp.status))
            current = urljoin(current, target)
        return Response(url=url, final_url=current, error="for mange redirects", redirects=redirects)

    def _once(self, url: str, method: str, accept: str, attempts: int = 3) -> Response:
        resp = self._attempt(url, method, accept)
        for n in range(1, attempts):
            if not resp.error:
                break
            time.sleep(0.6 * n)  # forbigående netværks-/TLS-fejl må ikke blive til falske SEO-fejl
            resp = self._attempt(url, method, accept)
        return resp

    def _attempt(self, url: str, method: str, accept: str) -> Response:
        req = urllib.request.Request(
            url,
            method=method,
            headers={"User-Agent": self.user_agent, "Accept": accept, "Accept-Encoding": "gzip, deflate"},
        )
        started = time.monotonic()
        try:
            try:
                raw = self._opener.open(req, timeout=self.timeout)
            except urllib.error.HTTPError as exc:  # 3xx/4xx/5xx
                raw = exc
            with raw:
                data = raw.read(MAX_BODY + 1) if method != "HEAD" else b""
                headers = {k.lower(): v for k, v in raw.headers.items()}
                status = raw.status if hasattr(raw, "status") else raw.code
        except Exception as exc:  # netværk, TLS, timeout
            return Response(url=url, final_url=url, error=f"{type(exc).__name__}: {exc}",
                            elapsed_ms=int((time.monotonic() - started) * 1000))
        elapsed = int((time.monotonic() - started) * 1000)
        transfer = len(data)
        enc = headers.get("content-encoding", "").lower()
        try:
            if enc == "gzip":
                data = gzip.decompress(data)
            elif enc == "deflate":
                data = zlib.decompress(data)
        except Exception:
            pass
        return Response(url=url, final_url=url, status=status, headers=headers, body=data[:MAX_BODY],
                        elapsed_ms=elapsed, transfer_size=transfer)

"""Server-side fetching of URLs a user (or a model) gave us – product pages and product images – without SSRF.

Rules, for every hop (the first URL and every redirect):
- only http/https, only the default ports (80/443), no user:password@ in the URL;
- the host is resolved here and EVERY address must be public (no loopback, private, link-local, CGNAT, multicast,
  reserved or unspecified ranges, IPv4-mapped IPv6 of those, or cloud metadata);
- the connection goes to the address we checked (the host name only travels in Host and TLS SNI/verification), so a
  DNS answer that changes between the check and the connect (DNS rebinding) cannot reach an internal address;
- redirects are followed by hand, at most MAX_REDIRECTS, each one checked again;
- a short timeout and a hard byte limit while streaming (the body is never read past the limit).

The content is returned as bytes/text and treated as data only: nothing from it is executed or rendered as HTML.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

UA = "Mozilla/5.0 (compatible; Dialogbot/1.0; +https://dialogbot.app)"
TIMEOUT = 8.0
MAX_REDIRECTS = 4
HTML_MAX_BYTES = 2_000_000
IMAGE_MAX_BYTES = 6 * 1024 * 1024


class FetchBlocked(Exception):
    """The URL may not be fetched (scheme, port, credentials or a non-public address). The message is for logs only."""


class FetchFailed(Exception):
    """Network error, timeout, bad status or a body over the limit."""


@dataclass
class Fetched:
    url: str           # the final URL after redirects
    status: int
    content_type: str
    body: bytes

    @property
    def text(self) -> str:
        enc = "utf-8"
        ct = self.content_type.lower()
        if "charset=" in ct:
            enc = ct.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        try:
            return self.body.decode(enc, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


def _public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return _public(ip.ipv4_mapped)
        if ip.sixtofour is not None or ip.teredo is not None:
            return False
    if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
            or ip.is_unspecified or not ip.is_global):
        return False
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"):
        return False  # CGNAT (is_global already says False on recent Pythons; kept explicit)
    return True


def resolve(host: str) -> list[str]:
    """All addresses of `host` (replaced in tests). Raises FetchFailed when it does not resolve."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as e:
        raise FetchFailed(f"dns: {host}") from e
    return sorted({i[4][0] for i in infos})


def check_url(url: str) -> tuple[str, str, int, str]:
    """(scheme, host, port, checked_ip) for a URL that may be fetched, else FetchBlocked."""
    try:
        u = urlsplit(url.strip())
    except ValueError as e:
        raise FetchBlocked("unparsable") from e
    if u.scheme not in ("http", "https"):
        raise FetchBlocked(f"scheme {u.scheme!r}")
    if u.username or u.password:
        raise FetchBlocked("credentials in url")
    host = (u.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise FetchBlocked("no host")
    try:
        port = u.port or (443 if u.scheme == "https" else 80)
    except ValueError as e:
        raise FetchBlocked("bad port") from e
    if port not in (80, 443):
        raise FetchBlocked(f"port {port}")
    if host in ("localhost", "metadata.google.internal") or host.endswith((".localhost", ".internal", ".local")):
        raise FetchBlocked("internal name")
    try:
        literal = ipaddress.ip_address(host)
        addrs = [str(literal)]
    except ValueError:
        addrs = resolve(host)
    if not addrs:
        raise FetchFailed("no address")
    for a in addrs:
        if not _public(ipaddress.ip_address(a.split("%")[0])):
            raise FetchBlocked(f"non-public address for {host}")
    return u.scheme, host, port, addrs[0].split("%")[0]


def _open(url: str, *, max_bytes: int, accept: str):
    """One hop: (status, headers, body) from the checked address. Replaced in tests."""
    import httpx

    scheme, host, port, ip = check_url(url)
    u = urlsplit(url)
    netloc = f"[{ip}]" if ":" in ip else ip
    if port not in (80, 443) or (scheme == "http" and port != 80) or (scheme == "https" and port != 443):
        netloc += f":{port}"
    target = urlunsplit((scheme, netloc, u.path or "/", u.query, ""))
    headers = {"host": host + ("" if port in (80, 443) else f":{port}"), "user-agent": UA,
               "accept": accept, "accept-language": "da,en;q=0.7"}
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False, trust_env=False) as c:
            req = c.build_request("GET", target, headers=headers,
                                  extensions={"sni_hostname": host} if scheme == "https" else {})
            r = c.send(req, stream=True)
            try:
                body = bytearray()
                if r.status_code < 300 or r.status_code >= 400:
                    for chunk in r.iter_bytes():
                        body += chunk
                        if len(body) > max_bytes:
                            raise FetchFailed("too large")
                return r.status_code, dict(r.headers), bytes(body)
            finally:
                r.close()
    except FetchFailed:
        raise
    except httpx.HTTPError as e:
        raise FetchFailed(type(e).__name__) from e


def fetch(url: str, *, max_bytes: int = HTML_MAX_BYTES, accept: str = "text/html,application/xhtml+xml") -> Fetched:
    current = url.strip()
    for _hop in range(MAX_REDIRECTS + 1):
        status, headers, body = _open(current, max_bytes=max_bytes, accept=accept)
        h = {k.lower(): v for k, v in headers.items()}
        if status in (301, 302, 303, 307, 308):
            loc = h.get("location")
            if not loc:
                raise FetchFailed("redirect without location")
            current = urljoin(current, loc)
            continue
        return Fetched(url=current, status=status, content_type=h.get("content-type", ""), body=body)
    raise FetchFailed("too many redirects")

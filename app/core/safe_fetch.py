"""One safe way to fetch a page from a website someone else controls (company research, knowledge import, social links).

Every request:
- http(s) only, ports 80/443 only, no credentials in the URL;
- the host is resolved once and EVERY address is checked (private, loopback, link-local, reserved, multicast,
  unspecified, IPv4-mapped/6to4/Teredo forms, cloud metadata) – then the connection goes to that validated address
  (the URL carries the IP, `Host` and TLS SNI carry the name), so a DNS answer that changes between the check and the
  connect (DNS rebinding) cannot reach an internal address;
- redirects are followed by hand (max 4), each hop checked again;
- robots.txt is fetched per host, cached 24 h, and honoured for our user agent;
- size and time limits per page; at most N concurrent fetches per host (process-wide).

The guard applies in dev and test too; ALLOW_PRIVATE_FETCH=true (refused outside dev/test) lets local tests reach a
site on this machine. Callers get `None`-free results: a refused or failed fetch raises FetchBlocked / FetchFailed.
"""
from __future__ import annotations

import ipaddress
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx

from app.config import get_settings

USER_AGENT = "DialogbotResearch/1.0 (+https://www.dialogbot.dk/privatliv)"
ROBOTS_AGENT = "DialogbotResearch"
MAX_REDIRECTS = 4
ROBOTS_TTL = 24 * 3600
ROBOTS_MAX_BYTES = 200_000
METADATA_HOSTS = {"metadata.google.internal", "metadata", "instance-data"}
_EXTRA_BLOCKED = [ipaddress.ip_network(n) for n in (
    "100.64.0.0/10",   # carrier-grade NAT (also Render/Tailscale-style internal ranges)
    "169.254.0.0/16",  # link-local, incl. 169.254.169.254 metadata
    "fd00::/8", "fc00::/7", "fe80::/10", "fec0::/10",
    "64:ff9b::/96",    # NAT64 can wrap a private IPv4
    "2001:db8::/32",
)]


class FetchBlocked(Exception):
    """The URL or the address it resolves to is not allowed. `reason` is a short machine word."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


class FetchFailed(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


@dataclass
class Page:
    url: str          # final URL after redirects
    status: int
    content_type: str
    body: bytes
    truncated: bool = False

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class Budget:
    """Limits for one research run. `pages_used` counts pages actually fetched (robots.txt is not a page)."""

    max_pages: int = 8
    page_bytes: int = 1_500_000
    timeout: float = 10.0
    pages_used: int = 0
    log: list[dict] = field(default_factory=list)

    @classmethod
    def from_settings(cls, max_pages: int | None = None) -> Budget:
        s = get_settings()
        return cls(max_pages=max_pages or s.sales_research_max_pages, page_bytes=s.sales_research_page_bytes,
                   timeout=s.sales_research_timeout_seconds)


Resolver = Callable[[str], list[str]]


def system_resolver(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as e:
        raise FetchFailed("dns", host) from e
    return list(dict.fromkeys(str(i[4][0]) for i in infos))


def ip_allowed(raw: str) -> bool:
    try:
        ip = ipaddress.ip_address(raw.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        for inner in (ip.ipv4_mapped, ip.sixtofour, (ip.teredo or (None, None))[1]):
            if inner is not None and not ip_allowed(str(inner)):
                return False
    if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
            or ip.is_unspecified or not ip.is_global):
        return False
    return not any(ip in n for n in _EXTRA_BLOCKED if n.version == ip.version)


def check_url(url: str) -> tuple[str, int]:
    """Static checks (scheme, port, credentials, host form). Returns (hostname, port)."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise FetchBlocked("scheme", p.scheme or "none")
    if p.username or p.password or "@" in (p.netloc or ""):
        raise FetchBlocked("credentials")
    host = (p.hostname or "").rstrip(".").lower()
    if not host:
        raise FetchBlocked("host")
    try:
        port = p.port or (443 if p.scheme == "https" else 80)
    except ValueError as e:
        raise FetchBlocked("port", "invalid") from e
    if port not in (80, 443):
        raise FetchBlocked("port", str(port))
    if host in METADATA_HOSTS or host == "localhost" or host.endswith((".localhost", ".internal", ".local")):
        raise FetchBlocked("private_address", host)
    return host, port


def resolve_checked(host: str, resolver: Resolver | None = None) -> str:
    """Resolve and validate every address; return the one to connect to."""
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
        ips = [str(literal)]
    except ValueError:
        ips = (resolver or system_resolver)(host)
    if not ips:
        raise FetchFailed("dns", host)
    if not get_settings().allow_private_fetch:
        bad = [ip for ip in ips if not ip_allowed(ip)]
        if bad:
            raise FetchBlocked("private_address", bad[0])
    return ips[0]


def _pinned(url: str, ip: str) -> tuple[str, str]:
    """(URL with the IP as host, Host header value)."""
    p = urlparse(url)
    host_for_url = f"[{ip}]" if ":" in ip else ip
    netloc = host_for_url if p.port is None else f"{host_for_url}:{p.port}"
    host_header = p.hostname if p.port is None else f"{p.hostname}:{p.port}"
    return urlunparse(p._replace(netloc=netloc)), host_header


_host_locks: dict[str, threading.BoundedSemaphore] = {}
_host_locks_guard = threading.Lock()


def _host_slot(host: str) -> threading.BoundedSemaphore:
    with _host_locks_guard:
        sem = _host_locks.get(host)
        if sem is None:
            sem = _host_locks[host] = threading.BoundedSemaphore(max(1, get_settings().sales_research_per_host_concurrency))
        return sem


def _one(client: httpx.Client, url: str, ip: str, host: str, *, max_bytes: int, timeout: float, method: str = "GET",
         content: bytes | None = None, headers: dict | None = None) -> tuple[httpx.Response, bytes, bool]:
    pinned, host_header = _pinned(url, ip)
    hdrs = httpx.Headers({"user-agent": USER_AGENT, "accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5"})
    hdrs.update(headers or {})
    hdrs["host"] = host_header
    req = client.build_request(method, pinned, content=content, headers=hdrs,
                               extensions={"sni_hostname": host, "timeout": {"connect": timeout, "read": timeout,
                                                                              "write": timeout, "pool": timeout}})
    started = time.monotonic()
    r = client.send(req, stream=True)
    try:
        body, truncated = b"", False
        for chunk in r.iter_bytes():
            body += chunk
            if len(body) > max_bytes:
                body, truncated = body[:max_bytes], True
                break
            if time.monotonic() - started > timeout:
                raise FetchFailed("timeout", url)
    finally:
        r.close()
    return r, body, truncated


_robots: dict[str, tuple[float, RobotFileParser | None]] = {}


def _robots_for(client: httpx.Client, scheme: str, host: str, ip: str, timeout: float) -> RobotFileParser | None:
    key = f"{scheme}://{host}"
    hit = _robots.get(key)
    if hit and time.time() - hit[0] < ROBOTS_TTL:
        return hit[1]
    parser: RobotFileParser | None = None
    try:
        r, body, _ = _one(client, f"{key}/robots.txt", ip, host, max_bytes=ROBOTS_MAX_BYTES, timeout=timeout)
        if r.status_code == 200:
            parser = RobotFileParser()
            parser.parse(body.decode("utf-8", errors="replace").splitlines())
        elif r.status_code in (401, 403):
            parser = RobotFileParser()
            parser.disallow_all = True
    except (httpx.HTTPError, FetchFailed):
        parser = None  # no robots.txt reachable: allowed, as crawlers conventionally treat it
    _robots[key] = (time.time(), parser)
    return parser


def clear_robots_cache() -> None:
    _robots.clear()


def get(url: str, *, budget: Budget | None = None, resolver: Resolver | None = None,
        transport: httpx.BaseTransport | None = None, robots: bool = True, html_only: bool = True) -> Page:
    """Fetch one page within `budget`. Raises FetchBlocked (not allowed) or FetchFailed (could not be fetched)."""
    budget = budget or Budget.from_settings()
    if budget.pages_used >= budget.max_pages:
        raise FetchBlocked("budget", f"{budget.max_pages} pages")
    with httpx.Client(follow_redirects=False, transport=transport, timeout=budget.timeout) as client:
        current = url
        for _hop in range(MAX_REDIRECTS + 1):
            host, _port = check_url(current)
            ip = resolve_checked(host, resolver)
            p = urlparse(current)
            if robots:
                rp = _robots_for(client, p.scheme, host, ip, budget.timeout)
                if rp is not None and not rp.can_fetch(ROBOTS_AGENT, current):
                    raise FetchBlocked("robots", current)
            with _host_slot(host):
                try:
                    r, body, truncated = _one(client, current, ip, host, max_bytes=budget.page_bytes,
                                              timeout=budget.timeout)
                except httpx.HTTPError as e:
                    raise FetchFailed("http_error", type(e).__name__) from e
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                current = urljoin(current, r.headers["location"])
                continue
            budget.pages_used += 1
            ctype = r.headers.get("content-type", "")
            budget.log.append({"url": current, "status": r.status_code, "bytes": len(body), "truncated": truncated})
            if r.status_code != 200:
                raise FetchFailed("status", str(r.status_code))
            if html_only and ctype and "html" not in ctype:
                raise FetchFailed("content_type", ctype[:60])
            return Page(url=current, status=r.status_code, content_type=ctype, body=body, truncated=truncated)
    raise FetchBlocked("redirects", url)


def send(method: str, url: str, *, content: bytes | None = None, headers: dict | None = None, timeout: float = 10.0,
         max_bytes: int = 64_000, resolver: Resolver | None = None, transport: httpx.BaseTransport | None = None) -> Page:
    """One request to the pinned, validated address – no redirects followed, no robots.txt (for deliveries such as
    outgoing webhooks, where the receiver gave us the URL). Any status is returned; a 3xx is NOT followed.
    Raises FetchBlocked (not allowed) or FetchFailed ("timeout", "http_error", "dns")."""
    host, _port = check_url(url)
    ip = resolve_checked(host, resolver)
    with httpx.Client(follow_redirects=False, transport=transport, timeout=timeout) as client, _host_slot(host):
        try:
            r, body, truncated = _one(client, url, ip, host, max_bytes=max_bytes, timeout=timeout, method=method,
                                      content=content, headers=headers)
        except httpx.TimeoutException as e:
            raise FetchFailed("timeout", url) from e
        except httpx.HTTPError as e:
            raise FetchFailed("http_error", type(e).__name__) from e
    return Page(url=url, status=r.status_code, content_type=r.headers.get("content-type", ""), body=body,
                truncated=truncated)


def get_html(url: str, **kw) -> tuple[str, str] | None:
    """Compatibility helper: (final_url, html) or None on any refusal or failure."""
    try:
        page = get(url, **kw)
    except (FetchBlocked, FetchFailed):
        return None
    return page.url, page.text

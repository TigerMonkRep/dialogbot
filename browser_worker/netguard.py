"""Network allow-list, enforced in the browser context (not in a prompt).

Every request the page makes (documents, XHR, images, scripts, iframes, redirects, WebSockets) passes `route`;
a host outside `allowed_domains` is aborted. A sub-domain of a listed host is allowed (`www.x.dk` for `x.dk`),
a parent domain is not. Prompt injection on a page therefore cannot send the agent, or its data, anywhere else.
"""
from __future__ import annotations

import ipaddress
from collections.abc import Callable
from urllib.parse import urlsplit


def normalize_domain(raw: str) -> str:
    """`https://WWW.Salon.dk:443/book` -> `www.salon.dk`. Raises ValueError on something that is not a host."""
    s = (raw or "").strip().lower()
    if "://" not in s:
        s = "//" + s
    host = urlsplit(s).hostname or ""
    host = host.rstrip(".")
    if not host or " " in host or "/" in host:
        raise ValueError(f"not a host: {raw!r}")
    return host


def normalize_domains(domains: list[str]) -> list[str]:
    out: list[str] = []
    for d in domains:
        h = normalize_domain(d)
        if h not in out:
            out.append(h)
    if not out:
        raise ValueError("allowed_domains must not be empty")
    return out


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def host_allowed(host: str | None, allowed: list[str]) -> bool:
    if not host:
        return False
    host = host.lower().rstrip(".")
    for d in allowed:
        if host == d:
            return True
        if not _is_ip(d) and host.endswith("." + d):
            return True
    return False


def url_allowed(url: str, allowed: list[str]) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if url == "about:blank":
        return True
    if parts.scheme not in ("http", "https", "ws", "wss"):
        return False
    return host_allowed(parts.hostname, allowed)


def chromium_args(allowed: list[str]) -> list[str]:
    """Layer 1, inside Chromium's network stack: everything is sent to a dead proxy except the allowed hosts.

    Playwright's `route()` is NOT invoked for the hops of a redirect after `continue_()`, so a 302 from an allowed page
    to a foreign host (or an internal IP such as 169.254.169.254) would slip past layer 2 (`install`). The bypass list
    is enforced by the browser itself for every request: redirect hops, IP literals, WebSockets, prefetch. A host that
    is not listed never reaches the network (the request fails with ERR_PROXY_CONNECTION_FAILED).
    """
    bypass = ["<-loopback>"]  # loopback is not implicitly bypassed; a loopback address works only if it is listed
    for d in allowed:
        bypass.append(d)
        if not _is_ip(d):
            bypass.append("*." + d)
    return [
        "--proxy-server=http://127.0.0.1:9", "--proxy-bypass-list=" + ";".join(bypass),
        ]


def install(context, allowed: list[str], on_block: Callable[[str], None]) -> None:
    """Install the guard on a Playwright BrowserContext (all pages, popups included, and WebSockets)."""

    def route(r):
        url = r.request.url
        if url_allowed(url, allowed):
            r.continue_()
        else:
            on_block(url)
            r.abort("blockedbyclient")

    def ws_route(ws):
        if url_allowed(ws.url, allowed):
            ws.connect_to_server()
        else:
            on_block(ws.url)
            ws.close(code=1008, reason="blocked")

    # Layer 2: Playwright route (clear errors, logging, WebSockets). Layer 1 is `chromium_args`.
    context.route("**/*", route)
    context.route_web_socket("**/*", ws_route)

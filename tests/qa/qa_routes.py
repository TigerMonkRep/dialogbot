"""Static route resolver for QA journey tests: does a link the product sends land on a real page?

Reads the routes from web/src/app (page.tsx / route.ts, route groups "(x)" ignored, [param] and [...rest] as wildcards),
the permanent and temporary redirects in web/next.config.ts and the /<locale>/ prefix of marketing pages.
`resolve("/onboarding/workspace")` → "/opsaetning/1"; a path that hits no route → None.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APP = os.path.join(ROOT, "web", "src", "app")
PUBLIC = os.path.join(ROOT, "web", "public")
LOCALES = ("da", "en", "de", "es", "fr", "it", "no", "sv")


@lru_cache(maxsize=1)
def _routes() -> list[tuple[str, str]]:
    out = []
    for dp, _dn, fn in os.walk(APP):
        if not {"page.tsx", "route.ts"} & set(fn):
            continue
        rel = os.path.relpath(dp, APP)
        segs = [s for s in ("" if rel == "." else rel).split("/") if s and not (s.startswith("(") and s.endswith(")"))]
        rx = ""
        for s in segs:
            rx += r"/.+" if s.startswith("[...") else r"/[^/]+" if s.startswith("[") else "/" + re.escape(s)
        out.append(("^" + (rx or "/") + "$", "/" + "/".join(segs)))
    return out


@lru_cache(maxsize=1)
def _redirects() -> list[tuple[str, str]]:
    src = open(os.path.join(ROOT, "web", "next.config.ts"), encoding="utf-8").read()
    pairs = re.findall(r'\["(/[^"]*)",\s*"(/[^"]*)"\]', src)
    pairs += re.findall(r'source:\s*"(/[^"]*)",\s*destination:\s*"(/[^"]*)"', src)
    return [(s, d) for s, d in pairs if "(" not in s]


def _redirect(path: str) -> str | None:
    for s, d in _redirects():
        rx = re.sub(r":(\w+)\*", r"(?P<\1>.*)", s)
        rx = "^" + re.sub(r":(\w+)(?![\w*])", r"(?P<\1>[^/]+)", rx) + "$"
        m = re.match(rx, path)
        if m:
            out = d
            for k, v in m.groupdict().items():
                out = out.replace(f":{k}*", v).replace(f":{k}", v)
            return out.split("?")[0]
    return None


def resolve(url: str, _depth: int = 0) -> str | None:
    """The route template a same-site URL or path finally lands on (after redirects), or None."""
    path = re.sub(r"^https?://[^/]+", "", url).split("#")[0].split("?")[0] or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    first = path.split("/")[1] if path.count("/") else ""
    if first in LOCALES:
        path = path[len(first) + 1:] or "/"
    nxt = _redirect(path)
    if nxt and _depth < 5:
        return resolve(nxt, _depth + 1)
    if "." in path.rsplit("/", 1)[-1] and os.path.isfile(os.path.join(PUBLIC, path.lstrip("/"))):
        return "public:" + path
    for rx, tpl in _routes():
        if re.match(rx, path):
            return tpl
    return None


def read(rel: str) -> str:
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()

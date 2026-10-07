"""Letvægts HTML-udtræk (kun standardbiblioteket) af de elementer, SEO-checks har brug for."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

_SKIP_TEXT = {"script", "style", "noscript", "template", "svg"}
_WORD = re.compile(r"[A-Za-zÆØÅæøåÉéÜü0-9][A-Za-zÆØÅæøåÉéÜü0-9'-]+")


@dataclass
class Image:
    src: str
    alt: str | None
    width: str | None
    height: str | None
    loading: str | None
    in_head_of_page: bool = False


@dataclass
class Link:
    href: str
    text: str
    rel: str
    nofollow: bool = False


@dataclass
class Page:
    url: str
    lang: str | None = None
    title: str | None = None
    meta: dict[str, str] = field(default_factory=dict)  # name/property (lowercase) -> content
    canonical: str | None = None
    hreflang: list[tuple[str, str]] = field(default_factory=list)
    headings: list[tuple[int, str]] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    jsonld_raw: list[str] = field(default_factory=list)
    scripts: list[dict[str, str]] = field(default_factory=list)
    stylesheets: list[str] = field(default_factory=list)
    icons: list[str] = field(default_factory=list)
    text: str = ""
    has_doctype: bool = False
    iframes: int = 0

    # --- afledt -------------------------------------------------------------
    @property
    def words(self) -> list[str]:
        return _WORD.findall(self.text)

    @property
    def h1(self) -> list[str]:
        return [t for lvl, t in self.headings if lvl == 1]

    @property
    def robots_directives(self) -> set[str]:
        out: set[str] = set()
        for key in ("robots", "googlebot"):
            out |= {d.strip().lower() for d in self.meta.get(key, "").split(",") if d.strip()}
        return out

    def jsonld(self) -> tuple[list[dict], list[str]]:
        """(objekter, fejl). Flader @graph ud."""
        objs: list[dict] = []
        errors: list[str] = []
        for raw in self.jsonld_raw:
            try:
                data = json.loads(raw)
            except ValueError as exc:
                errors.append(str(exc)[:80])
                continue
            stack = data if isinstance(data, list) else [data]
            for item in stack:
                if isinstance(item, dict):
                    if isinstance(item.get("@graph"), list):
                        objs.extend(g for g in item["@graph"] if isinstance(g, dict))
                    else:
                        objs.append(item)
        return objs, errors

    def schema_types(self) -> set[str]:
        types: set[str] = set()
        for obj in self.jsonld()[0]:
            t = obj.get("@type")
            for name in (t if isinstance(t, list) else [t]):
                if isinstance(name, str):
                    types.add(name)
        return types

    def internal_links(self) -> list[Link]:
        host = urlparse(self.url).netloc.lower().removeprefix("www.")
        out = []
        for ln in self.links:
            p = urlparse(ln.href)
            if p.scheme in ("http", "https") and p.netloc.lower().removeprefix("www.") == host:
                out.append(ln)
        return out


class _Extractor(HTMLParser):
    def __init__(self, url: str):
        super().__init__(convert_charrefs=True)
        self.page = Page(url=url)
        self._in_head = False
        self._title: list[str] | None = None
        self._heading: tuple[int, list[str]] | None = None
        self._link: tuple[dict[str, str], list[str]] | None = None
        self._jsonld: list[str] | None = None
        self._skip = 0
        self._text: list[str] = []
        self._img_index = 0

    def handle_decl(self, decl: str) -> None:
        if decl.lower().startswith("doctype"):
            self.page.has_doctype = True

    def handle_starttag(self, tag: str, attrs_list) -> None:
        a = {k.lower(): (v or "") for k, v in attrs_list}
        p = self.page
        if tag == "html":
            p.lang = a.get("lang") or None
        elif tag == "head":
            self._in_head = True
        elif tag == "title" and p.title is None:
            self._title = []
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or a.get("http-equiv") or "").lower()
            if key and "content" in a:
                p.meta.setdefault(key, a["content"])
            if "charset" in a:
                p.meta.setdefault("charset", a["charset"])
        elif tag == "link":
            rel = a.get("rel", "").lower()
            href = a.get("href", "")
            if "canonical" in rel and href:
                p.canonical = href
            elif "alternate" in rel and a.get("hreflang") and href:
                p.hreflang.append((a["hreflang"], href))
            elif "stylesheet" in rel and href:
                p.stylesheets.append(urljoin(p.url, href))
            elif "icon" in rel and href:
                p.icons.append(urljoin(p.url, href))
        elif tag == "script":
            if a.get("type", "").lower() == "application/ld+json":
                self._jsonld = []
            else:
                p.scripts.append({"src": urljoin(p.url, a["src"]) if a.get("src") else "",
                                  "async": "async" in a, "defer": "defer" in a or a.get("type") == "module",
                                  "in_head": self._in_head, "type": a.get("type", ""), "nomodule": "nomodule" in a})
            self._skip += 1
        elif tag in ("style", "noscript", "template", "svg"):
            self._skip += 1
        elif len(tag) == 2 and tag[0] == "h" and tag[1] in "123456":
            self._heading = (int(tag[1]), [])
        elif tag == "a" and a.get("href") is not None:
            self._link = (a, [])
        elif tag == "img":
            self._img_index += 1
            p.images.append(Image(src=a.get("src") or a.get("data-src", ""), alt=a.get("alt"),
                                  width=a.get("width"), height=a.get("height"),
                                  loading=a.get("loading"), in_head_of_page=self._img_index <= 2))
        elif tag == "iframe":
            p.iframes += 1

    def handle_endtag(self, tag: str) -> None:
        p = self.page
        if tag == "head":
            self._in_head = False
        elif tag == "title" and self._title is not None:
            p.title = " ".join("".join(self._title).split())
            self._title = None
        elif tag == "script":
            if self._jsonld is not None:
                p.jsonld_raw.append("".join(self._jsonld))
                self._jsonld = None
            self._skip = max(0, self._skip - 1)
        elif tag in ("style", "noscript", "template", "svg"):
            self._skip = max(0, self._skip - 1)
        elif self._heading and tag == f"h{self._heading[0]}":
            lvl, parts = self._heading
            p.headings.append((lvl, " ".join("".join(parts).split())))
            self._heading = None
        elif tag == "a" and self._link:
            attrs, parts = self._link
            rel = attrs.get("rel", "").lower()
            p.links.append(Link(href=urljoin(p.url, attrs["href"]) if attrs["href"] else "",
                                text=" ".join("".join(parts).split()) or attrs.get("aria-label", ""),
                                rel=rel, nofollow="nofollow" in rel))
            self._link = None

    def handle_data(self, data: str) -> None:
        if self._title is not None:
            self._title.append(data)
        if self._jsonld is not None:
            self._jsonld.append(data)
            return
        if self._heading:
            self._heading[1].append(data)
        if self._link:
            self._link[1].append(data)
        if not self._skip and not self._in_head:
            self._text.append(data)


def parse_html(html: str, url: str) -> Page:
    ex = _Extractor(url)
    try:
        ex.feed(html)
        ex.close()
    except Exception:  # defekt HTML må aldrig vælte en scanning
        pass
    ex.page.text = " ".join(" ".join(ex._text).split())
    return ex.page

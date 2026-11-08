"""What a shop's product page SAYS about the product, read from its structured data – never guessed.

Sources, best first: schema.org JSON-LD (Product, ProductGroup with hasVariant, also inside @graph), then microdata-free
meta tags (Open Graph `og:*`, `product:price:amount` / `product:price:currency`), then <title>. A price is only taken
together with an explicit ISO currency from the same source; a price in running text («129 kr.») is NOT used. Stock
and sizes are only what the page declares. Variants come only from hasVariant / offers the page lists.

The HTML is parsed with the standard library's tokenizer as data: no script is run, no style or markup is kept.
"""
from __future__ import annotations

import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Currencies with a minor unit other than 2 (ISO 4217). Everything else we see in Danish shops has 2.
MINOR_DIGITS = {"JPY": 0, "KRW": 0, "ISK": 0, "CLP": 0, "BHD": 3, "KWD": 3, "OMR": 3, "JOD": 3, "TND": 3}
AVAILABILITY = {"instock": "in_stock", "outofstock": "out_of_stock", "preorder": "preorder", "backorder": "backorder",
                "limitedavailability": "limited", "soldout": "out_of_stock", "discontinued": "discontinued",
                "instoreonly": "in_store_only", "onlineonly": "in_stock"}
# Only pure tracking parameters are removed; everything else (variant=, size=, sku=, color= …) is kept as is.
TRACKING = re.compile(r"^(utm_[a-z]+|fbclid|gclid|gbraid|wbraid|msclkid|mc_eid|mc_cid|_hsenc|_hsmi|srsltid)$", re.I)


def clean_url(url: str) -> str:
    u = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if not TRACKING.match(k)]
    return urlunsplit((u.scheme.lower(), u.netloc.lower(), u.path, urlencode(q, doseq=True), ""))


def to_minor(value, currency: str) -> int | None:
    """«1.299,00», «1299.00», 1299 → 129900 (DKK). None for anything that is not a plain non-negative amount."""
    if value is None or isinstance(value, bool):
        return None
    s = str(value).strip().replace(" ", "").replace(" ", "")
    if not s or not re.fullmatch(r"\d[\d.,]*", s):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if len(s.rsplit(",", 1)[1]) in (1, 2) else s.replace(",", "")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.rsplit(".", 1)[1]) == 3):
        s = s.replace(".", "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    digits = MINOR_DIGITS.get(currency, 2)
    minor = int((d * (10 ** digits)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return minor if 0 <= minor < 10**12 else None


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.ld: list[str] = []
        self.title = ""
        self.canonical: str | None = None
        self._in_ld = False
        self._in_title = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").strip().lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "script" and a.get("type", "").lower().strip() == "application/ld+json":
            self._in_ld, self._buf = True, []
        elif tag == "title" and not self.title:
            self._in_title, self._buf = True, []
        elif tag == "link" and "canonical" in a.get("rel", "").lower() and a.get("href"):
            self.canonical = a["href"]

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self.ld.append("".join(self._buf))
            self._in_ld = False
        elif tag == "title" and self._in_title:
            self.title = " ".join("".join(self._buf).split())
            self._in_title = False

    def handle_data(self, data):
        if self._in_ld or self._in_title:
            self._buf.append(data)


def _nodes(obj):
    if isinstance(obj, list):
        for x in obj:
            yield from _nodes(x)
    elif isinstance(obj, dict):
        yield obj
        for k in ("@graph", "mainEntity", "itemListElement"):
            if k in obj:
                yield from _nodes(obj[k])


def _types(node: dict) -> set[str]:
    t = node.get("@type")
    return {str(x).split("/")[-1].lower() for x in (t if isinstance(t, list) else [t]) if x}


def _text(v, n: int = 200) -> str | None:
    if isinstance(v, dict):
        v = v.get("name") or v.get("@value")
    if isinstance(v, list):
        v = next((x for x in v if isinstance(x, str)), None)
    if v is None or isinstance(v, (dict, list, bool)):
        return None
    s = " ".join(unescape(str(v)).split())
    return s[:n] or None


def _image(v, base: str) -> str | None:
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict):
        v = v.get("url") or v.get("contentUrl")
    if not isinstance(v, str) or not v.strip():
        return None
    u = urljoin(base, v.strip())
    return u[:1000] if u.startswith(("https://", "http://")) else None


def _offer(node: dict) -> dict | None:
    """The first offer with an explicit currency: {price_minor, currency, availability, url}."""
    offers = node.get("offers")
    for o in _nodes(offers) if offers is not None else []:
        if not isinstance(o, dict):
            continue
        cur = _text(o.get("priceCurrency"), 3)
        price = o.get("price", o.get("lowPrice"))
        if price is None and isinstance(o.get("priceSpecification"), dict):
            price = o["priceSpecification"].get("price")
            cur = cur or _text(o["priceSpecification"].get("priceCurrency"), 3)
        cur = cur.upper() if cur else None
        out = {"availability": _availability(o.get("availability")), "url": _text(o.get("url"), 1000)}
        if cur and re.fullmatch(r"[A-Z]{3}", cur) and (m := to_minor(price, cur)) is not None:
            return out | {"price_minor": m, "currency": cur}
        if out["availability"]:
            return out | {"price_minor": None, "currency": None}
    return None


def _availability(v) -> str | None:
    s = _text(v, 120)
    if not s:
        return None
    return AVAILABILITY.get(s.rstrip("/").split("/")[-1].lower())


def _variant_of(node: dict, base: str) -> dict:
    off = _offer(node) or {}
    v = {"name": _text(node.get("name"), 160), "size": _text(node.get("size"), 80),
         "color": _text(node.get("color"), 80), "sku": _text(node.get("sku"), 80),
         "url": _image(node.get("url") or off.get("url"), base), "image_url": _image(node.get("image"), base),
         "price_minor": off.get("price_minor"), "currency": off.get("currency"),
         "availability": off.get("availability")}
    for p in node.get("additionalProperty") or []:  # some shops put size/colour there
        if isinstance(p, dict):
            nm, val = (_text(p.get("name"), 40) or "").lower(), _text(p.get("value"), 80)
            if nm in ("size", "størrelse", "str.", "str") and not v["size"]:
                v["size"] = val
            elif nm in ("color", "colour", "farve") and not v["color"]:
                v["color"] = val
    return {k: x for k, x in v.items() if x is not None}


def _same(a: str | None, b: str) -> bool:
    if not a:
        return False
    try:
        return clean_url(a) == clean_url(b)
    except ValueError:
        return False


def parse(html: str, url: str) -> dict:
    """{title, image_url, price_minor, currency, shop, brand, sku, availability, description, options, selected,
    found} – every value only when the page declares it."""
    c = _Collector()
    try:
        c.feed(html[:HTML_LIMIT])
        c.close()
    except Exception:  # noqa: BLE001 – broken markup: use what was collected
        pass
    out: dict = {}
    product, group = None, None
    for raw in c.ld:
        try:
            data = json.loads(raw.strip().strip(";"))
        except ValueError:
            continue
        for n in _nodes(data):
            ts = _types(n)
            if "productgroup" in ts and group is None:
                group = n
            elif "product" in ts and product is None:
                product = n
    main = product or group
    variants: list[dict] = []
    if group is not None:
        variants = [_variant_of(v, url) for v in _nodes(group.get("hasVariant") or []) if "product" in _types(v)]
    elif product is not None and isinstance(product.get("isVariantOf"), dict):
        variants = [_variant_of(v, url) for v in _nodes(product["isVariantOf"].get("hasVariant") or [])]
    selected = next((v for v in variants if _same(v.get("url"), url)), None)
    if main is not None:
        out["title"] = _text(main.get("name"), 300)
        out["image_url"] = _image(main.get("image"), url)
        out["brand"] = _text(main.get("brand"), 120)
        out["sku"] = _text(main.get("sku"), 80)
        out["description"] = _text(main.get("description"), 500)
        off = _offer(main) or (_offer(group) if group is not None and main is not group else None)
        if off:
            out["availability"] = off.get("availability")
            if off.get("price_minor") is not None:
                out["price_minor"], out["currency"] = off["price_minor"], off["currency"]
        if _text(main.get("size"), 80):
            out["size"] = _text(main.get("size"), 80)
        if _text(main.get("color"), 80):
            out["color"] = _text(main.get("color"), 80)
    if selected:  # the URL points at one variant: its own facts win
        for k in ("price_minor", "currency", "availability", "image_url", "size", "color", "sku"):
            if selected.get(k) is not None:
                out[k] = selected[k]
        if selected.get("name"):
            out["variant"] = selected["name"]
    m = c.meta
    out.setdefault("title", None)
    if not out.get("title"):
        out["title"] = _text(m.get("og:title") or m.get("twitter:title") or c.title, 300)
    if not out.get("image_url"):
        out["image_url"] = _image(m.get("og:image:secure_url") or m.get("og:image") or m.get("twitter:image"), url)
    if out.get("price_minor") is None:
        cur = (m.get("product:price:currency") or m.get("og:price:currency") or "").strip().upper()
        amount = m.get("product:price:amount") or m.get("og:price:amount")
        if re.fullmatch(r"[A-Z]{3}", cur) and (mm := to_minor(amount, cur)) is not None:
            out["price_minor"], out["currency"] = mm, cur
    if not out.get("availability"):
        out["availability"] = _availability(m.get("product:availability") or m.get("og:availability"))
    out["shop"] = _text(m.get("og:site_name"), 120)
    out["description"] = out.get("description") or _text(m.get("og:description") or m.get("description"), 500)
    opts = {"sizes": _uniq(v.get("size") for v in variants), "colors": _uniq(v.get("color") for v in variants),
            "variants": [{k: v[k] for k in ("name", "size", "color", "sku", "url", "price_minor", "currency",
                                            "availability") if k in v} for v in variants[:60]]}
    out["options"] = opts if (opts["sizes"] or opts["colors"] or opts["variants"]) else None
    out["found"] = bool(out.get("title") and (main is not None or out.get("image_url") or out.get("price_minor")))
    return {k: v for k, v in out.items() if v is not None}


HTML_LIMIT = 1_500_000


def _uniq(xs) -> list[str]:
    seen: list[str] = []
    for x in xs:
        if x and x not in seen:
            seen.append(x)
    return seen[:40]

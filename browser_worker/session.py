"""One tethered browser session = one Playwright context, no shared state between runs.

The seven tools the agent may use (and nothing else): navigate, read_page, click, type, select, wait, screenshot.
Every call is budgeted, logged in `steps` (with a screenshot) and passes the hard limits in code:

1. network allow-list (netguard) on the whole context;
2. `type`/`select` refuse password, card number, CVC, expiry and CPR fields  -> RunFailed("forbidden_field");
3. `click` refuses commit buttons (Bekræft/Book nu/Betal/Send ...) unless the run is approved
   -> ApprovalRequired (and only ONE such click per approval);
4. CAPTCHA and login walls -> FallbackPhone; nothing is solved or logged in;
5. max_steps / max_seconds -> FallbackPhone.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from . import limits, netguard, page_reader
from .errors import ApprovalRequired, FallbackPhone, RunFailed, ToolError

VIEWPORT = {"width": 1280, "height": 720}
NAV_TIMEOUT_MS = 15_000
ACTION_TIMEOUT_MS = 8_000
MAX_WAIT_MS = 5_000
MAX_TYPE_CHARS = 500
TOOL_NAMES = ("navigate", "read_page", "click", "type", "select", "wait", "screenshot")


@dataclass
class Budget:
    max_steps: int = 25
    max_seconds: int = 180


@dataclass
class Step:
    n: int
    tool: str
    arg: str
    result: str = ""
    screenshot_file: str | None = None
    at: str = ""


@dataclass
class BrowserSession:
    allowed_domains: list[str]
    budget: Budget = field(default_factory=Budget)
    approved: bool = False
    record_video: bool = True
    workdir: Path | None = None
    headless: bool = True
    chromium_path: str | None = field(default_factory=lambda: os.environ.get("BROWSER_CHROMIUM_PATH") or None)
    clock: Callable[[], float] = time.monotonic
    # host -> ip, resolved and checked before launch and pinned in Chromium (--host-resolver-rules) against DNS rebinding
    pins: dict[str, str] = field(default_factory=dict)
    # checks a sub-domain's addresses the first time it is used (raises when they are internal)
    address_check: Callable[[str], None] | None = None
    # called before every tool call; True = the run was cancelled elsewhere (e.g. «ring i stedet»)
    cancel_check: Callable[[], bool] | None = None

    def __post_init__(self) -> None:
        self.allowed_domains = netguard.normalize_domains(self.allowed_domains)
        self.steps: list[Step] = []
        self.blocked: list[str] = []
        self.elements: list[dict] = []
        self.commits_used = 0
        self._own_workdir = self.workdir is None
        self._pw = self._browser = self._ctx = self.page = None
        self._t0 = 0.0
        self._paused = 0.0
        self._last_page: dict = {}
        self._video = None

    # --- lifecycle -------------------------------------------------------------------------------------------
    def __enter__(self) -> BrowserSession:
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def start(self) -> None:
        if self.workdir is None:
            self.workdir = Path(tempfile.mkdtemp(prefix="browser-run-"))
        (self.workdir / "shots").mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        kw = {"headless": self.headless, "args": netguard.chromium_args(self.allowed_domains, self.pins)}
        if self.chromium_path:
            kw["executable_path"] = self.chromium_path
        self._browser = self._pw.chromium.launch(**kw)
        ctx_kw: dict = {
            "viewport": VIEWPORT, "locale": "da-DK", "timezone_id": "Europe/Copenhagen",
            "service_workers": "block", "accept_downloads": False, "permissions": [], "java_script_enabled": True,
        }
        if self.record_video:
            ctx_kw["record_video_dir"] = str(self.workdir / "video")
            ctx_kw["record_video_size"] = VIEWPORT
        self._ctx = self._browser.new_context(**ctx_kw)
        self._ctx.set_default_timeout(ACTION_TIMEOUT_MS)
        self._ctx.set_default_navigation_timeout(NAV_TIMEOUT_MS)
        netguard.install(self._ctx, self.allowed_domains, self._on_block, pinned=set(self.pins),
                         address_check=self.address_check)
        self._ctx.on("requestfailed", self._on_failed)
        self.page = self._ctx.new_page()
        self.page.on("popup", self._on_popup)
        self._t0 = self.clock()

    def _on_block(self, url: str) -> None:
        if len(self.blocked) < 50:
            self.blocked.append(url[:300])

    def _on_failed(self, request) -> None:
        """A request the browser itself refused (layer 1): record it like a layer-2 block."""
        failure = request.failure or ""
        if "PROXY" in failure or "TUNNEL" in failure or "BLOCKED_BY_CLIENT" in failure:
            if not netguard.url_allowed(request.url, self.allowed_domains):
                self._on_block(request.url)

    def _on_popup(self, popup) -> None:
        self.page = popup  # a booking flow that opens a new tab continues there; the context guard covers it too
        popup.on("popup", self._on_popup)

    def close(self) -> Path | None:
        """Close the context (this finalises the video) and return the video path, if any. Idempotent."""
        video = None
        try:
            if self._ctx is not None:
                pages = list(self._ctx.pages)
                vids = [p.video for p in pages if p.video]
                self._ctx.close()
                for v in vids:
                    try:
                        video = Path(v.path())
                        break
                    except PlaywrightError:
                        continue
        finally:
            for closer in (self._browser, self._pw):
                try:
                    if closer is not None:
                        closer.close() if closer is self._browser else closer.stop()
                except PlaywrightError:
                    pass
            self._ctx = self._browser = self._pw = self.page = None
        if video is not None:
            self._video = video
        return self._video

    def cleanup(self) -> None:
        """Delete every local file of this run (screenshots, video, temp). Call after the evidence was uploaded."""
        if self.workdir and self._own_workdir:
            shutil.rmtree(self.workdir, ignore_errors=True)

    @property
    def video_path(self) -> Path | None:
        return self._video

    def elapsed(self) -> float:
        """Active time: waiting for a human's approval (`hold`) does not use up the run's max_seconds."""
        return self.clock() - self._t0 - self._paused

    @contextmanager
    def hold(self):
        t = self.clock()
        try:
            yield
        finally:
            self._paused += self.clock() - t

    # --- step bookkeeping ------------------------------------------------------------------------------------
    def _begin(self, tool: str, arg: str) -> Step:
        step = Step(n=len(self.steps) + 1, tool=tool, arg=arg[:300], at=datetime.now(UTC).isoformat())
        self.steps.append(step)
        if self.cancel_check is not None and self.cancel_check():
            step.result = "cancelled"
            raise FallbackPhone("cancelled", "Kørslen er annulleret")
        if step.n > self.budget.max_steps:
            step.result = "budget: max_steps"
            raise FallbackPhone("budget_steps", f"Over {self.budget.max_steps} trin")
        if self.elapsed() > self.budget.max_seconds:
            step.result = "budget: max_seconds"
            raise FallbackPhone("budget_time", f"Over {self.budget.max_seconds} sekunder")
        return step

    def _shot(self, step: Step) -> None:
        if self.page is None:
            return
        path = self.workdir / "shots" / f"step-{step.n:02d}.png"
        try:
            self.page.screenshot(path=str(path), timeout=5000)
            step.screenshot_file = str(path)
        except PlaywrightError:
            pass

    def _run(self, tool: str, arg: str, fn: Callable[[Step], str], *, shot: bool = True) -> str:
        step = self._begin(tool, arg)
        try:
            out = fn(step)
            step.result = step.result or out[:300]
            return out
        except ToolError as e:
            step.result = f"error: {e.code}"
            raise
        except (ApprovalRequired, RunFailed, FallbackPhone) as e:
            step.result = f"{e.status}: {e.error_code}"
            raise
        finally:
            if shot:
                self._shot(step)

    # --- the seven tools -------------------------------------------------------------------------------------
    def navigate(self, url: str) -> str:
        def go(step: Step) -> str:
            if not netguard.url_allowed(url, self.allowed_domains):
                self._on_block(url)
                raise ToolError("domain_not_allowed", "Adressen ligger uden for de godkendte domæner.")
            try:
                self.page.goto(url, wait_until="domcontentloaded")
            except PlaywrightError as e:
                self._navigation_error(e)
            self._after_navigation()
            return f"OK {self.page.url}"

        return self._run("navigate", url, go)

    def read_page(self) -> str:
        def read(step: Step) -> str:
            self._check_walls()
            data = self.page.evaluate(page_reader.READ_JS)
            self.elements = data["elements"]
            self._last_page = data
            return page_reader.format_page(data)

        out = self._run("read_page", "", read)
        self.steps[-1].result = f"{len(self.elements)} elementer"
        return out

    def click(self, ref: str, *, commit: bool = False) -> str:
        """`commit=True` is for playbooks that KNOW this is the confirming click: it is then treated as one even if
        its label is innocent. The LLM tool schema has no such argument."""

        def do(step: Step) -> str:
            loc, facts = self._resolve(ref)
            label = self._label_of(facts)
            step.arg = f"{ref} «{label[:80]}»"
            hit = limits.matches_forbidden_click(facts["text"], facts["aria_label"], facts["value"], facts["title"],
                                                 facts["img_alt"]) or ("commit" if commit else None)
            if hit:
                if not self.approved:
                    raise ApprovalRequired(label or hit)
                if self.commits_used >= 1:
                    raise RunFailed("commit_limit", "Kun ét bekræft-klik pr. godkendelse")
                self.commits_used += 1
            if facts["disabled"]:
                raise ToolError("disabled", "Elementet er deaktiveret.")
            try:
                loc.click()
                self.page.wait_for_load_state("domcontentloaded")
            except PlaywrightError as e:
                self._navigation_error(e)
            self._after_navigation()
            if not hit:
                self._check_unexpected_commit(step)
            return f"OK {self.page.url}"

        return self._run("click", ref, do)

    def type(self, ref: str, text: str) -> str:
        def do(step: Step) -> str:
            loc, facts = self._resolve(ref)
            self._guard_field(facts)
            if facts["tag"] not in ("input", "textarea") or facts["type"] in ("file", "hidden", "checkbox", "radio",
                                                                              "submit", "button", "image", "reset"):
                raise ToolError("not_typeable", "Elementet kan ikke udfyldes med tekst.")
            if facts["disabled"] or facts["readonly"]:
                raise ToolError("disabled", "Feltet kan ikke redigeres.")
            step.arg = f"{ref} «{self._label_of(facts)[:60]}» = {text[:MAX_TYPE_CHARS]!r}"
            try:
                loc.fill(text[:MAX_TYPE_CHARS])
            except PlaywrightError as e:
                raise ToolError("type_failed", str(e).splitlines()[0][:200]) from e
            self._check_walls()
            return "OK"

        return self._run("type", ref, do)

    def select(self, ref: str, value: str) -> str:
        def do(step: Step) -> str:
            loc, facts = self._resolve(ref)
            self._guard_field(facts)
            if facts["tag"] != "select":
                raise ToolError("not_select", "Elementet er ikke en rulleliste.")
            step.arg = f"{ref} «{self._label_of(facts)[:60]}» = {value[:100]!r}"
            try:
                try:
                    loc.select_option(value=value, timeout=2000)
                except PlaywrightError:
                    loc.select_option(label=value, timeout=2000)
            except PlaywrightError as e:
                raise ToolError("select_failed", "Valget findes ikke i listen.") from e
            return "OK"

        return self._run("select", ref, do)

    def wait(self, ms: int) -> str:
        def do(step: Step) -> str:
            self.page.wait_for_timeout(max(0, min(int(ms), MAX_WAIT_MS)))
            self._check_walls()
            self._check_unexpected_commit(step)
            return "OK"

        return self._run("wait", str(ms), do)

    def screenshot(self) -> str:
        def do(step: Step) -> str:
            return f"screenshot step-{step.n:02d}"

        return self._run("screenshot", "", do)

    # --- helpers ---------------------------------------------------------------------------------------------
    def find(self, role: str, pattern: str, *, nth: int = 0) -> str | None:
        """Ref of the nth element of `role` whose name matches the regex (case-insensitive), from the last read_page."""
        rx = re.compile(pattern, re.IGNORECASE)
        hits = [e for e in self.elements if e["role"] == role and rx.search(e.get("name", ""))]
        return hits[nth]["ref"] if len(hits) > nth else None

    def page_text(self) -> list[str]:
        """The `text`/`heading` lines of the last read_page (for before→after summaries)."""
        return [ln for ln in self._last_page.get("lines", []) if ln.startswith(("text ", "heading"))]

    def field_values(self) -> dict[str, str]:
        """Label -> value for the text fields on the last-read page. Forbidden fields are never included."""
        out: dict[str, str] = {}
        for ln in self._last_page.get("lines", []):
            m = re.match(r'\[e\d+\] textbox "(.*?)"(?: .*?)? value="(.*?)"$', ln)
            if m and not limits.matches_forbidden_field(m.group(1)):
                out[m.group(1)] = m.group(2)
        return out

    def back(self) -> str:
        """Playbook helper: one step back in history (logged as a navigate; same allow-list and wall checks)."""

        def do(step: Step) -> str:
            try:
                self.page.go_back(wait_until="domcontentloaded")
            except PlaywrightError as e:
                self._navigation_error(e)
            self._after_navigation()
            return f"OK {self.page.url}"

        return self._run("navigate", "back", do)

    def receipt_pdf(self, path: Path) -> Path:
        self.page.pdf(path=str(path), format="A4", print_background=True)
        return path

    def final_screenshot(self, path: Path) -> Path:
        self.page.screenshot(path=str(path), full_page=True)
        return path

    def _resolve(self, ref: str):
        if not re.fullmatch(r"e\d{1,5}", ref or "") or not any(e["ref"] == ref for e in self.elements):
            raise ToolError("unknown_ref", "Ukendt ref. Kald read_page og brug en ref fra den.")
        loc = self.page.locator(f'[data-dbref="{ref}"]')
        try:
            if loc.count() != 1:
                raise ToolError("unknown_ref", "Siden har ændret sig. Kald read_page igen.")
            return loc, loc.evaluate(page_reader.ELEMENT_FACTS_JS)
        except PlaywrightError as e:
            raise ToolError("unknown_ref", "Siden har ændret sig. Kald read_page igen.") from e

    @staticmethod
    def _label_of(f: dict) -> str:
        return f["aria_label"] or f["text"] or f["value"] or f["label"] or f["placeholder"] or f["title"] or f["img_alt"]

    @staticmethod
    def _guard_field(f: dict) -> None:
        if f["type"] == "password":
            raise RunFailed("forbidden_field", "Adgangskodefelter udfyldes aldrig.")
        hit = limits.matches_forbidden_field(f["field_name"], f["autocomplete"], f["label"], f["aria_label"],
                                             f["placeholder"], f["id"])
        if hit:
            raise RunFailed("forbidden_field", f"Feltet ser ud til at være et forbudt felt ({hit}).")

    def _check_unexpected_commit(self, step: Step) -> None:
        """Safety net for a commit button with an innocent label («Næste» that really books). A click we did not flag as
        committing led to a page that reads like a receipt and offers nothing left to confirm: the booking may have been
        made without a human yes. Stop, keep url + screenshot, and let the caller tell the user (A3) so they can cancel."""
        if self.approved or self.commits_used or self.page is None:
            return
        try:
            facts = self.page.evaluate(page_reader.CAPTCHA_LOGIN_JS, [])
            names = self.page.evaluate(page_reader.CLICKABLE_NAMES_JS)
        except PlaywrightError:
            return
        left = any(limits.matches_forbidden_click(n) for n in names)
        phrase = limits.looks_like_receipt(facts["text"], commit_buttons_left=left)
        if phrase:
            self._shot(step)
            raise RunFailed("unexpected_commit", "Siden ligner en kvittering, selvom der ikke var givet godkendelse.",
                            details={"url": self.page.url, "phrase": phrase, "step": step.n,
                                     "screenshot_file": step.screenshot_file})

    def _after_navigation(self) -> None:
        if self.page.url.startswith("chrome-error:"):  # a link whose target the allow-list aborted
            try:
                self.page.go_back(wait_until="domcontentloaded")
            except PlaywrightError:
                pass
            if any(limits.is_captcha_url(u) for u in self.blocked):
                raise FallbackPhone("captcha", "CAPTCHA fundet")
            raise ToolError("blocked_by_allowlist", "Linket peger uden for de godkendte domæner.")
        self._check_walls()

    def _navigation_error(self, e: PlaywrightError) -> None:
        msg = str(e)
        if any(m in msg for m in ("ERR_BLOCKED_BY_CLIENT", "net::ERR_ABORTED", "ERR_PROXY_CONNECTION_FAILED",
                                  "ERR_TUNNEL_CONNECTION_FAILED")):
            if any(limits.is_captcha_url(u) for u in self.blocked):
                raise FallbackPhone("captcha", "CAPTCHA fundet")
            raise ToolError("blocked_by_allowlist", "Siden prøvede at sende os til et domæne, der ikke er godkendt.")
        raise ToolError("navigation_failed", msg.splitlines()[0][:200])

    def _check_walls(self) -> None:
        """CAPTCHA and login detection. Nothing is solved, nothing is logged in; the run falls back to the phone."""
        if self.page is None or self.page.url == "about:blank":
            return
        try:
            facts = self.page.evaluate(page_reader.CAPTCHA_LOGIN_JS, list(limits.CAPTCHA_SELECTORS))
        except PlaywrightError:
            return  # mid-navigation; the next call checks again
        if (any(limits.is_captcha_url(u) for u in facts["frames"] + facts["scripts"] + self.blocked)
                or facts["marked"]):
            raise FallbackPhone("captcha", "CAPTCHA fundet")
        if facts["password_field"] or limits.LOGIN_TEXT_RE.search(facts["text"]):
            raise FallbackPhone("login_required", "Siden kræver login")

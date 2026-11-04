"""A1: the tethered session against the local OnlineBooq clone. No network, no real sites."""
from __future__ import annotations

import pytest

from browser_worker import limits, netguard
from browser_worker.errors import ApprovalRequired, FallbackPhone, RunFailed, ToolError
from browser_worker.session import BrowserSession, Budget


def session(site, workdir, **kw):
    kw.setdefault("record_video", False)
    return BrowserSession(allowed_domains=["127.0.0.1"], workdir=workdir, **kw)


def go(s, text_pattern, role="link"):
    s.read_page()
    ref = s.find(role, text_pattern)
    assert ref, f"no {role} matching {text_pattern!r}"
    return s.click(ref)


def walk_to_summary(s, site):
    s.navigate(site.url + "/booking/ydelse.html")
    go(s, "Herreklip")
    go(s, "Ingen præference")
    go(s, "Tirsdag 10")
    go(s, "10:30")
    s.read_page()
    s.type(s.find("textbox", "Navn"), "Mette Hansen")
    s.type(s.find("textbox", "Telefon"), "+4512345678")
    s.click(s.find("button", "Fortsæt"))


# --- pure units -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("label", ["Bekræft booking", "BOOK NU", "Gennemfør køb", "Betal nu", "Send", "Confirm", "Submit",
                                   "Pay now", "Complete booking", "Bekræfter...", "Bestil tid"])
def test_forbidden_click_words(label):
    assert limits.matches_forbidden_click(label)


@pytest.mark.parametrize("label", ["Fortsæt", "Tilbage", "Herreklip – 30 min – 350 kr.", "Algemene vilkår", "Næste", "10:30"])
def test_harmless_click_words(label):
    assert not limits.matches_forbidden_click(label)


@pytest.mark.parametrize("label", ["Adgangskode", "password", "Kortnummer", "cc-number", "CVC", "cvv", "Udløbsdato", "CPR-nummer",
                                   "cc-exp", "Card number", "personnummer"])
def test_forbidden_field_words(label):
    assert limits.matches_forbidden_field(label)


@pytest.mark.parametrize("label", ["Navn", "Telefon", "E-mail", "Besked til frisøren", "Kommentar", "tel", "email", "name"])
def test_harmless_field_words(label):
    assert not limits.matches_forbidden_field(label)


def test_host_allowlist_rules():
    a = netguard.normalize_domains(["https://WWW.Salon.dk/book", "salon.dk"])
    assert a == ["www.salon.dk", "salon.dk"]
    assert netguard.host_allowed("www.salon.dk", a)
    assert netguard.host_allowed("book.salon.dk", a)  # sub-domain of a listed host
    assert not netguard.host_allowed("salon.dk.evil.com", a)
    assert not netguard.host_allowed("evilsalon.dk", a)
    assert not netguard.host_allowed("dk", a)
    assert netguard.host_allowed("127.0.0.1", ["127.0.0.1"])
    assert not netguard.host_allowed("1.127.0.0.1", ["127.0.0.1"])
    assert not netguard.url_allowed("file:///etc/passwd", a)
    assert not netguard.url_allowed("javascript:alert(1)", a)
    with pytest.raises(ValueError):
        netguard.normalize_domains([])


def test_captcha_urls():
    assert limits.is_captcha_url("https://www.google.com/recaptcha/api2/anchor")
    assert limits.is_captcha_url("//hcaptcha.com/1/api.js")
    assert not limits.is_captcha_url("https://salon.dk/booking")


# --- network allow-list -----------------------------------------------------------------------------------------

def test_allowlist_blocks_foreign_requests_and_redirects(site, workdir):
    with session(site, workdir) as s:
        s.navigate(site.url + "/booking-evil/ydelse.html")
        # the page tried to load a pixel from a foreign host: aborted by the context guard, not by the page
        assert any("evil.invalid/pixel.png" in u for u in s.blocked)
        with pytest.raises(ToolError) as e:
            s.navigate("http://evil.invalid/")
        assert e.value.code == "domain_not_allowed"
        s.read_page()
        with pytest.raises(ToolError) as e:  # prompt-injection link: the guard aborts the navigation
            s.click(s.find("link", "Se tilbuddet nu"))
        assert e.value.code == "blocked_by_allowlist"
        with pytest.raises(ToolError) as e:  # an allowed page that redirects to a foreign host
            s.navigate(site.url + "/redirect-out")
        assert e.value.code == "blocked_by_allowlist"
        assert any("evil.invalid" in u for u in s.blocked)
        # the session still works afterwards, and is still on the allowed site
        s.navigate(site.url + "/booking/ydelse.html")
        assert "Vælg ydelse" in s.read_page()


def test_redirect_to_other_ip_never_reaches_the_network(site, workdir):
    """Playwright's route() is not called for redirect hops; the browser-level layer must stop this one."""
    with session(site, workdir) as s:
        with pytest.raises(ToolError) as e:
            s.navigate(site.url + "/redirect-ip")
        assert e.value.code == "blocked_by_allowlist"
        assert "127.0.0.2" not in site.hosts  # the server never saw a request for the foreign address
        assert any("127.0.0.2" in u for u in s.blocked)


def test_subdomain_of_listed_host_is_allowed(site, workdir):
    with BrowserSession(allowed_domains=["localhost"], workdir=workdir, record_video=False) as s:
        s.navigate(f"http://shop.localhost:{site.port}/index.html")
        assert "Salon Test" in s.read_page()
        with pytest.raises(ToolError):
            s.navigate(f"http://127.0.0.1:{site.port}/index.html")


# --- read_page ----------------------------------------------------------------------------------------------------

def test_read_page_is_compact_text_not_html(site, workdir):
    with session(site, workdir) as s:
        s.navigate(site.url + "/booking/ydelse.html")
        out = s.read_page()
    assert "<" not in out and "style" not in out
    assert 'heading1 "Vælg ydelse"' in out
    assert '[e1] link "OnlineBooq' not in out  # header text is not a link
    assert 'link "Herreklip – 30 min – 350 kr."' in out
    assert out.count("[e") >= 4


def test_refs_come_from_the_latest_read_page(site, workdir):
    with session(site, workdir) as s:
        s.navigate(site.url + "/booking/ydelse.html")
        with pytest.raises(ToolError) as e:
            s.click("e1")  # nothing read yet
        assert e.value.code == "unknown_ref"
        s.read_page()
        ref = s.find("link", "Herreklip")
        s.click(ref)
        with pytest.raises(ToolError) as e:  # the page changed: the old ref is dead until the next read_page
            s.click(ref)
        assert e.value.code in ("unknown_ref",)
        with pytest.raises(ToolError):
            s.click("'] , body")  # not even a ref


# --- forbidden fields -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("label", ["Kortnummer", "CPR-nummer", "Udløbsdato", "CVC"])
def test_type_refuses_forbidden_fields(site, workdir, label):
    with session(site, workdir) as s:
        s.navigate(site.url + "/booking-felter/kontakt.html")
        s.read_page()
        assert s.type(s.find("textbox", "Navn"), "Mette") == "OK"
        ref = s.find("textbox", label)
        assert ref, label
        with pytest.raises(RunFailed) as e:
            s.type(ref, "1234 5678 9012 3456")
        assert e.value.error_code == "forbidden_field"
        s.read_page()
        # nothing was written to the field, and forbidden fields never appear in the form summary
        assert all(v != "1234 5678 9012 3456" for v in s.field_values().values())
        assert list(s.field_values()) == ["Navn"]


def test_password_field_is_never_typed_and_means_login_wall(site, workdir):
    assert pytest.raises(RunFailed, BrowserSession._guard_field,
                         {"type": "password", "field_name": "", "autocomplete": "", "label": "", "aria_label": "",
                          "placeholder": "", "id": ""}).value.error_code == "forbidden_field"
    with session(site, workdir) as s:
        with pytest.raises(FallbackPhone) as e:
            s.navigate(site.url + "/booking-login/ydelse.html")
        assert e.value.error_code == "login_required"


def test_select_also_refuses_forbidden_fields():
    facts = {"type": "", "field_name": "cc-exp-month", "autocomplete": "", "label": "", "aria_label": "", "placeholder": "",
             "id": ""}
    with pytest.raises(RunFailed):
        BrowserSession._guard_field(facts)


# --- forbidden clicks / approval --------------------------------------------------------------------------------

def test_confirm_click_needs_approval_and_exactly_one_commit(site, workdir):
    with session(site, workdir) as s:
        walk_to_summary(s, site)
        s.read_page()
        assert "Bekræft booking" in "\n".join(s.page_text() + [e["name"] for e in s.elements])
        confirm = s.find("button", "Bekræft")
        with pytest.raises(ApprovalRequired) as e:
            s.click(confirm)
        assert "Bekræft booking" in e.value.label
        assert s.steps[-1].result.startswith("awaiting_approval")
        assert not any(h.startswith("/booking/kvittering") for h in site.hits)  # nothing was confirmed on the site
        # the session is still alive and unchanged: summary can be read for before→after
        assert "Mette Hansen" in s.read_page()

    with session(site, workdir, approved=True) as s:
        walk_to_summary(s, site)
        s.read_page()
        s.click(s.find("button", "Bekræft"))
        out = s.read_page()
        assert "Tak – din tid er booket" in out and "OB-20261110-0042" in out
        assert any(h.startswith("/booking/kvittering") for h in site.hits)
        # approval covers ONE confirming click: back on the summary, a second confirm is refused
        s.navigate(site.url + "/booking/oversigt.html?service=Herreklip&navn=Mette")
        s.read_page()
        with pytest.raises(RunFailed) as e:
            s.click(s.find("button", "Bekræft"))
        assert e.value.error_code == "commit_limit"


def test_playbook_commit_flag_forces_approval_even_for_innocent_label(site, workdir):
    with session(site, workdir) as s:
        walk_to_summary(s, site)
        s.read_page()
        with pytest.raises(ApprovalRequired):
            s.click(s.find("link", "Tilbage"), commit=True)


# --- CAPTCHA / login --------------------------------------------------------------------------------------------

def test_captcha_iframe_means_phone_fallback(site, workdir):
    with session(site, workdir) as s:
        with pytest.raises(FallbackPhone) as e:
            s.navigate(site.url + "/booking-captcha/ydelse.html")
        assert e.value.error_code == "captcha"
        assert e.value.status == "fallback_phone"


# --- budget -----------------------------------------------------------------------------------------------------

def test_max_steps_exceeded_means_phone_fallback(site, workdir):
    with session(site, workdir, budget=Budget(max_steps=3, max_seconds=60)) as s:
        s.navigate(site.url + "/booking-loop/side.html")
        s.read_page()
        s.read_page()
        with pytest.raises(FallbackPhone) as e:
            s.read_page()
        assert e.value.error_code == "budget_steps"
        assert s.steps[-1].result == "budget: max_steps"


def test_max_seconds_exceeded_means_phone_fallback(site, workdir):
    t = [0.0]
    with session(site, workdir, budget=Budget(max_steps=50, max_seconds=10), clock=lambda: t[0]) as s:
        s.navigate(site.url + "/booking-loop/side.html")
        t[0] = 11.0
        with pytest.raises(FallbackPhone) as e:
            s.read_page()
        assert e.value.error_code == "budget_time"


# --- logging and evidence ---------------------------------------------------------------------------------------

def test_every_call_is_logged_with_screenshot_and_video_is_cleaned_up(site, workdir):
    s = BrowserSession(allowed_domains=["127.0.0.1"], workdir=workdir, record_video=True)
    s.start()
    s.navigate(site.url + "/booking/ydelse.html")
    s.read_page()
    s.wait(50)
    s.screenshot()
    video = s.close()
    assert [st.tool for st in s.steps] == ["navigate", "read_page", "wait", "screenshot"]
    assert [st.n for st in s.steps] == [1, 2, 3, 4]
    for st in s.steps:
        assert st.screenshot_file and (workdir / "shots" / f"step-{st.n:02d}.png").stat().st_size > 0
        assert st.at
    assert video is not None and video.stat().st_size > 0
    s.close()  # idempotent
    s.cleanup()  # a caller-supplied workdir is the caller's to delete
    assert workdir.exists()


def test_own_workdir_is_deleted_by_cleanup(site):
    s = BrowserSession(allowed_domains=["127.0.0.1"], record_video=True)
    s.start()
    s.navigate(site.url + "/booking/ydelse.html")
    wd = s.workdir
    s.close()
    assert wd.exists()
    s.cleanup()
    assert not wd.exists()


# --- extended word list ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("label", ["Indsend", "indsender formularen", "Tilmeld", "Opret booking", "Opret booking nu"])
def test_added_commit_words(label):
    assert limits.matches_forbidden_click(label)


@pytest.mark.parametrize("label", ["Fortsæt", "Næste", "Videre", "Opret", "Tilbage"])
def test_wizard_steps_stay_harmless(label):
    assert not limits.matches_forbidden_click(label)


# --- safety net: an innocent-looking button that really books --------------------------------------------------

def test_unexpected_commit_is_caught_when_next_really_books(site, workdir):
    with session(site, workdir) as s:
        s.navigate(site.url + "/booking-sneaky/ydelse.html")
        go(s, "Herreklip")
        go(s, "Ingen præference")
        go(s, "Tirsdag 10")
        go(s, "10:30")
        s.read_page()
        s.type(s.find("textbox", "Navn"), "Mette Hansen")
        s.type(s.find("textbox", "Telefon"), "+4512345678")
        with pytest.raises(RunFailed) as e:
            s.click(s.find("button", "Næste"))  # label is innocent: the guard does not stop the click ...
        assert e.value.error_code == "unexpected_commit"  # ... but the receipt that follows is caught
        d = e.value.details
        assert d["url"].endswith("/booking-sneaky/slut.html") or "/slut.html" in d["url"]
        assert d["screenshot_file"] and (workdir / "shots").exists()
        assert any(h.startswith("/booking-sneaky/slut") for h in site.hits)  # honest: the site HAD been committed


def test_summary_page_titled_bekraeftelse_is_not_flagged(site, workdir):
    with session(site, workdir) as s:
        s.navigate(site.url + "/booking/oversigt-bekraeftelse.html?service=Herreklip&navn=Mette")
        s.wait(10)  # the page says «Bekræftelse», but its confirm button is still there: not a receipt, no false alarm


def test_wait_also_catches_a_delayed_commit(site, workdir):
    with session(site, workdir) as s:
        s.navigate(site.url + "/booking/kvittering.html?service=Herreklip&navn=Mette")
        with pytest.raises(RunFailed) as e:
            s.wait(10)
        assert e.value.error_code == "unexpected_commit"


def test_approved_run_may_see_the_receipt(site, workdir):
    with session(site, workdir, approved=True) as s:
        s.navigate(site.url + "/booking/kvittering.html?service=Herreklip&navn=Mette")
        s.wait(10)  # no unexpected_commit: this run was approved

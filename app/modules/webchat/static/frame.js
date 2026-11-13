/* Dialogbot chat frame (runs on the API origin inside the widget iframe). */
(function () {
  "use strict";
  var app = document.getElementById("app");
  var cfg = JSON.parse(app.getAttribute("data-config"));
  var store = "dialogbot:" + cfg.key;
  var state = null; // { id, token }
  try { state = JSON.parse(sessionStorage.getItem(store) || "null"); } catch (e) { state = null; }

  app.innerHTML =
    '<header><div><strong>Digital assistent</strong><span>AI · svarer ud fra virksomhedens godkendte oplysninger</span></div>' +
    '<button type="button" class="close" aria-label="Luk chat">×</button></header>' +
    '<ol class="log" aria-live="polite" aria-label="Samtale"></ol>' +
    '<p class="notice">Du skriver med en AI-assistent. Svar kan være ufuldstændige – del ikke følsomme oplysninger.</p>' +
    '<div class="contact-bar"><button type="button" class="contact-open">Bliv kontaktet af en medarbejder</button>' +
    '<button type="button" class="book-open" hidden>Book en tid</button></div>' +
    '<form class="book" hidden novalidate><strong>Book en tid</strong>' +
    '<label>Hvad drejer det sig om?<select name="type"></select></label>' +
    '<label>Tidspunkt<select name="start" required></select></label>' +
    '<label>Navn<input name="name" autocomplete="name" maxlength="200" required></label>' +
    '<label>Telefon<input name="phone" type="tel" autocomplete="tel" maxlength="40"></label>' +
    '<label>E-mail<input name="email" type="email" autocomplete="email" maxlength="320"></label>' +
    '<label class="check"><input name="consent" type="checkbox" required> Virksomheden må kontakte mig om aftalen.</label>' +
    '<p class="err" role="alert" hidden></p>' +
    '<div class="row"><button type="button" class="book-cancel">Annullér</button><button type="submit">Book</button></div></form>' +
    '<form class="contact" hidden novalidate><strong>Bliv kontaktet</strong>' +
    '<label>Navn<input name="name" autocomplete="name" maxlength="200" required></label>' +
    '<label>E-mail<input name="email" type="email" autocomplete="email" maxlength="320"></label>' +
    '<label>Telefon<input name="phone" type="tel" autocomplete="tel" maxlength="40"></label>' +
    '<label>Hvornår må vi ringe?<select name="window"><option value="">Ingen præference</option></select></label>' +
    '<label class="check"><input name="consent" type="checkbox" required> Virksomheden må kontakte mig om min henvendelse.</label>' +
    '<p class="err" role="alert" hidden></p>' +
    '<div class="row"><button type="button" class="contact-cancel">Annullér</button><button type="submit">Send</button></div></form>' +
    '<div class="code-step" role="group" aria-label="Bekræft dit nummer" hidden><strong>Bekræft dit nummer</strong><p class="hint"></p>' +
    '<label>Kode fra SMS<input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}"></label>' +
    '<p class="err" role="alert" hidden></p><p class="ok" role="status" hidden></p>' +
    '<div class="row"><button type="button" class="code-back">Ret nummer</button><button type="button" class="code-resend"></button>' +
    '<button type="button" class="code-submit">Bekræft</button></div></div>' +
    '<form><label for="msg" class="sr">Din besked</label><textarea id="msg" rows="2" maxlength="' + cfg.maxChars +
    '" placeholder="Skriv din besked…"></textarea><button type="submit">Send</button></form>';
  var log = app.querySelector(".log");
  var form = app.querySelector("form:not(.contact):not(.book)");
  var codeForm = app.querySelector(".code-step"); // not a <form>: the chat's own message form stays the only other one
  var contactForm = app.querySelector("form.contact");
  var contactBar = app.querySelector(".contact-bar");
  var bookForm = app.querySelector("form.book");
  var bookOpen = app.querySelector(".book-open");
  var input = app.querySelector("textarea");
  var send = form.querySelector("button");
  app.querySelector(".close").addEventListener("click", function () {
    if (window.parent !== window) window.parent.postMessage({ type: "dialogbot:close" }, "*");
  });

  var seen = {}; // ids of assistant/staff messages already on screen (visitor lines are drawn locally)
  var waitingNoted = false;
  var polling = null, pollUntil = 0;
  function label(role) { return role === "staff" ? "Medarbejder" : ""; }
  function show(m) {
    if (m.role === "visitor" || seen[m.id]) return;
    seen[m.id] = true;
    var li = bubble(m.role === "staff" ? "staff" : "assistant", m.text);
    if (m.role === "staff") li.setAttribute("data-label", label(m.role));
  }
  function poll() {
    if (!state || Date.now() > pollUntil) { clearInterval(polling); polling = null; return; }
    api("GET", "/conversations/" + state.id + "/messages").then(function (j) { j.messages.forEach(show); }).catch(function () {});
  }
  function keepPolling() {
    pollUntil = Date.now() + 30 * 60 * 1000; // stop after 30 minutes without activity
    if (!polling) polling = setInterval(poll, 5000);
  }

  function bubble(role, text, extra) {
    var li = document.createElement("li");
    li.className = "msg " + role + (extra ? " " + extra : "");
    li.textContent = text; // never innerHTML: replies are untrusted text
    log.appendChild(li);
    log.scrollTop = log.scrollHeight;
    return li;
  }
  function api(method, path, body) {
    var h = { "content-type": "application/json" };
    if (state) h["x-visitor-token"] = state.token;
    return fetch(cfg.base + "/" + encodeURIComponent(cfg.key) + path, {
      method: method, headers: h, body: body ? JSON.stringify(body) : undefined, credentials: "omit"
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) {
          var err = new Error(j.message || "Fejl"); err.status = r.status; err.code = j.code;
          err.retryAfter = j.retry_after; err.attemptsLeft = j.attempts_left; throw err;
        }
        return j;
      });
    });
  }
  var windowsLoaded = false;
  function loadWindows() {
    if (windowsLoaded) return;
    windowsLoaded = true;
    api("GET", "/callback-windows").then(function (j) {
      var sel = contactForm.elements.window;
      j.options.forEach(function (o) { var op = document.createElement("option"); op.value = o.key; op.textContent = o.label; sel.appendChild(op); });
    }).catch(function () { windowsLoaded = false; });
  }
  contactBar.querySelector("button").addEventListener("click", function () {
    loadWindows();
    contactForm.hidden = false; contactBar.hidden = true; contactForm.querySelector("input[name=name]").focus();
  });
  contactForm.querySelector(".contact-cancel").addEventListener("click", function () {
    contactForm.hidden = true; contactBar.hidden = false;
  });
  contactForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var f = contactForm.elements, err = contactForm.querySelector(".err");
    var body = { name: f.name.value.trim(), email: f.email.value.trim() || null, phone: f.phone.value.trim() || null,
                 note: "", consent: f.consent.checked, window: f.window.value || null };
    var problem = !body.name ? "Skriv dit navn." : (!body.email && !body.phone) ? "Skriv e-mail eller telefonnummer."
      : (body.window && !body.phone) ? "Skriv dit telefonnummer, så vi kan ringe dig op."
      : !body.consent ? "Sæt flueben, så virksomheden må kontakte dig." : "";
    if (problem) { err.textContent = problem; err.hidden = false; return; }
    err.hidden = true;
    // A phone number the visitor has not proven in this conversation is answered with `verification_required` → code step
    sendContact(body);
  });
  function sendContact(body) {
    var err = contactForm.querySelector(".err");
    ensureConversation()
      .then(function (s) { return api("POST", "/conversations/" + s.id + "/contact", body); })
      .then(function (j) {
        contactForm.hidden = true; codeForm.hidden = true;
        var li = bubble("system-ok", "Tak, " + body.name + "! Virksomheden kontakter dig hurtigst muligt.");
        manageLink(li, j.manage_url, "Aflys opringningen eller ret dine valg");
      })
      .catch(function (x) {
        if (x.code === "verification_required") { pendingContact = body; askCode(body.phone); return; }
        codeForm.hidden = true; contactForm.hidden = false;
        err.textContent = x.status === 422 ? "Tjek e-mail og telefonnummer." : (x.message || "Det lykkedes ikke. Prøv igen."); err.hidden = false;
      });
  }

  // W04: the number is proven with a 6-digit SMS code before the business may call it.
  var pendingContact = null, verification = null, resendTimer = null, checking = false;
  var codeErr = codeForm.querySelector(".err"), codeOk = codeForm.querySelector(".ok"), codeHint = codeForm.querySelector(".hint");
  var resend = codeForm.querySelector(".code-resend"), codeInput = codeForm.querySelector("input[name=code]");
  function codeError(text) { codeErr.textContent = text; codeErr.hidden = false; codeOk.hidden = true; }
  function cooldown(seconds) {
    clearInterval(resendTimer);
    var left = seconds;
    function tick() {
      if (left <= 0) { clearInterval(resendTimer); resend.disabled = false; resend.textContent = "Send ny kode"; return; }
      resend.disabled = true; resend.textContent = "Send ny kode (" + left + " s)"; left -= 1;
    }
    tick(); resendTimer = setInterval(tick, 1000);
  }
  function askCode(phone) {
    var err = contactForm.querySelector(".err");
    ensureConversation()
      .then(function (s) { return api("POST", "/conversations/" + s.id + "/contact/code", { phone: phone }); })
      .then(function (j) {
        verification = j.verification_id;
        contactForm.hidden = true; codeForm.hidden = false; codeErr.hidden = true; codeOk.hidden = true;
        codeHint.textContent = "Vi har sendt en kode på 6 cifre til " + j.phone_display + ". Den gælder i 10 minutter.";
        codeInput.value = ""; codeInput.disabled = false; codeInput.focus();
        cooldown(j.resend_after || 30);
      })
      .catch(function (x) {
        if (!codeForm.hidden) {
          if (x.code === "too_soon") { cooldown(x.retryAfter || 30); codeError("Vent et øjeblik, før du beder om en ny kode."); }
          else codeError(x.message || "Koden kunne ikke sendes. Prøv igen.");
          return;
        }
        err.textContent = x.code === "phone_invalid" ? "Tjek telefonnummeret." : x.status === 422 ? "Tjek e-mail og telefonnummer."
          : x.code === "too_soon" ? "Vent et øjeblik, før du beder om en ny kode."
          : (x.message || "Koden kunne ikke sendes. Prøv igen.");
        err.hidden = false;
      });
  }
  resend.addEventListener("click", function () { if (pendingContact) askCode(pendingContact.phone); });
  codeForm.querySelector(".code-back").addEventListener("click", function () {
    clearInterval(resendTimer); codeForm.hidden = true; contactForm.hidden = false; contactForm.elements.phone.focus();
  });
  codeInput.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); checkCode(); } });
  codeForm.querySelector(".code-submit").addEventListener("click", checkCode);
  function checkCode() {
    var code = codeInput.value.replace(/\s/g, "");
    if (!/^[0-9]{6}$/.test(code)) { codeError("Skriv de 6 cifre fra SMS'en."); return; }
    if (checking) return; // a double click checks the code once
    checking = true; codeErr.hidden = true;
    api("POST", "/conversations/" + state.id + "/contact/verify", { verification_id: verification, code: code })
      .finally(function () { checking = false; })
      .then(function () {
        clearInterval(resendTimer);
        codeOk.textContent = "Nummeret er bekræftet."; codeOk.hidden = false; codeInput.disabled = true;
        sendContact(pendingContact);
      })
      .catch(function (x) {
        if (x.code === "code_invalid") {
          codeError(x.attemptsLeft > 0 ? "Koden passer ikke. Du har " + x.attemptsLeft + (x.attemptsLeft === 1 ? " forsøg" : " forsøg") + " tilbage."
            : "Koden passer ikke. Bed om en ny kode.");
          if (!(x.attemptsLeft > 0)) { resend.disabled = false; resend.textContent = "Send ny kode"; clearInterval(resendTimer); }
        } else if (x.code === "too_many_attempts") {
          codeError("For mange forsøg. Bed om en ny kode."); clearInterval(resendTimer); resend.disabled = false; resend.textContent = "Send ny kode";
        } else if (x.code === "code_expired") {
          codeError("Koden er udløbet. Bed om en ny kode."); clearInterval(resendTimer); resend.disabled = false; resend.textContent = "Send ny kode";
        } else codeError(x.message || "Det lykkedes ikke. Prøv igen.");
      });
  }

  /** The customer's secure link (W09/W13) under a confirmation. Built with DOM nodes, only http(s) URLs. */
  function manageLink(li, url, text) {
    if (typeof url !== "string" || !/^https?:\/\//.test(url)) return;
    var a = document.createElement("a");
    a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.className = "manage"; a.textContent = text;
    li.appendChild(document.createElement("br")); li.appendChild(a);
  }

  // Online booking: shown only when the business has it switched on.
  function fillSlots(j) {
    var types = bookForm.elements.type, starts = bookForm.elements.start;
    if (!types.options.length) j.types.forEach(function (t) { var o = document.createElement("option"); o.value = t.id; o.textContent = t.name; types.appendChild(o); });
    types.value = j.type_id; starts.innerHTML = "";
    if (!j.slots.length) { var o = document.createElement("option"); o.value = ""; o.textContent = "Ingen ledige tider lige nu"; starts.appendChild(o); }
    j.slots.forEach(function (x) { var o = document.createElement("option"); o.value = x.start; o.textContent = x.label; starts.appendChild(o); });
  }
  api("GET", "/booking").then(function (j) { if (j.enabled) { bookOpen.hidden = false; fillSlots(j); } }).catch(function () {});
  bookOpen.addEventListener("click", function () {
    bookForm.hidden = false; contactBar.hidden = true; bookForm.elements.type.focus();
  });
  bookForm.elements.type.addEventListener("change", function () {
    api("GET", "/booking?type_id=" + encodeURIComponent(bookForm.elements.type.value)).then(fillSlots).catch(function () {});
  });
  bookForm.querySelector(".book-cancel").addEventListener("click", function () { bookForm.hidden = true; contactBar.hidden = false; });
  bookForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var f = bookForm.elements, err = bookForm.querySelector(".err");
    var body = { type_id: f.type.value, start: f.start.value, name: f.name.value.trim(), email: f.email.value.trim() || null,
                 phone: f.phone.value.trim() || null, note: "", consent: f.consent.checked };
    var problem = !body.start ? "Vælg et tidspunkt." : !body.name ? "Skriv dit navn." : (!body.email && !body.phone) ? "Skriv telefon eller e-mail."
      : !body.consent ? "Sæt flueben, så virksomheden må kontakte dig om aftalen." : "";
    if (problem) { err.textContent = problem; err.hidden = false; return; }
    err.hidden = true;
    ensureConversation()
      .then(function (s) { return api("POST", "/conversations/" + s.id + "/booking", body); })
      .then(function (j) {
        bookForm.hidden = true;
        // "pending": the business's calendar could not be read – the time is noted, a staff member confirms it
        var li = bubble("system-ok", j.confirmation === "pending"
          ? "Tak, " + body.name + "! Din tid " + j.label + " er noteret. En medarbejder bekræfter tiden."
          : "Tak, " + body.name + "! Du er booket " + j.label + ".");
        manageLink(li, j.manage_url, "Se, flyt eller aflys din tid");
      })
      .catch(function (x) {
        err.textContent = x.code === "slot_taken" ? "Tiden blev lige taget – vælg en anden." : x.status === 422 ? "Tjek telefon og e-mail." : (x.message || "Det lykkedes ikke. Prøv igen.");
        err.hidden = false;
        if (x.code === "slot_taken") bookForm.elements.type.dispatchEvent(new Event("change"));
      });
  });

  function disable(text) {
    input.disabled = true; send.disabled = true;
    if (text) bubble("system", text);
  }

  if (!cfg.available) { bubble("system", cfg.unavailable); disable(); contactBar.hidden = true; return; }
  bubble("assistant", cfg.greeting);
  if (state) {
    api("GET", "/conversations/" + state.id + "/messages").then(function (j) {
      j.messages.forEach(function (m) {
        if (m.role === "visitor") bubble("visitor", m.text); else show(m);
      });
      keepPolling();
    }).catch(function () { state = null; sessionStorage.removeItem(store); });
  }

  function ensureConversation() {
    if (state) return Promise.resolve(state);
    return api("POST", "/conversations", { host_origin: cfg.hostOrigin }).then(function (j) {
      state = { id: j.conversation_id, token: j.visitor_token };
      try { sessionStorage.setItem(store, JSON.stringify(state)); } catch (e) { /* private mode */ }
      return state;
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    bubble("visitor", text);
    var typing = bubble("assistant", "Skriver…", "typing");
    send.disabled = true;
    ensureConversation()
      .then(function (s) { return api("POST", "/conversations/" + s.id + "/messages", { text: text }); })
      .then(function (j) {
        typing.remove();
        keepPolling();
        if (j.reply) { seen[j.reply.id] = true; bubble("assistant", j.reply.text); }
        else if (j.waiting_for_staff && !waitingNoted) { waitingNoted = true; bubble("system-ok", "En medarbejder svarer dig her i chatten."); }
      })
      .catch(function (err) {
        typing.remove();
        if (err.status === 401) { state = null; sessionStorage.removeItem(store); }
        bubble("system", err.message || "Beskeden kunne ikke sendes. Prøv igen.");
        if (err.code === "conversation_limit" || err.code === "daily_limit" || err.code === "webchat_unavailable") disable();
      })
      .then(function () { if (!input.disabled) { send.disabled = false; input.focus(); } });
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
})();

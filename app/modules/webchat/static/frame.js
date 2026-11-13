/* Dialogbot chat frame (runs on the API origin inside the widget iframe). */
(function () {
  "use strict";
  var app = document.getElementById("app");
  var cfg = JSON.parse(app.getAttribute("data-config"));
  var store = "dialogbot:" + cfg.key;
  var state = null; // { id, token }
  try { state = JSON.parse(sessionStorage.getItem(store) || "null"); } catch (e) { state = null; }
  // Texts in the widget's language (app/modules/webchat/texts.py, chosen by the frame endpoint); Danish is the source.
  var lang = cfg.lang || "da", TX = cfg.t || {};
  function T(key, vars) {
    var s = TX[key] || key;
    if (vars) Object.keys(vars).forEach(function (k) { s = s.split("{" + k + "}").join(String(vars[k])); });
    return s;
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function E(key) { return esc(T(key)); }
  /** A server message in Danish is shown as is; in another language the code's own text (or a general one). */
  function msg(x, fallbackKey) {
    var byCode = { too_soon: "tooSoon", sms_rate_limited: "smsRateLimited", phone_invalid: "errPhone",
      code_expired: "codeExpired", too_many_attempts: "tooMany", slot_taken: "slotTaken", rate_limited: "busy",
      conversation_limit: "conversationLimit", daily_limit: "dailyLimit", webchat_unavailable: "unavailable" };
    if (lang === "da" && x && x.message) return x.message;
    return T((x && byCode[x.code]) || fallbackKey);
  }

  app.innerHTML =
    '<header><div><strong>' + E("title") + '</strong><span>' + E("subtitle") + '</span></div>' +
    '<button type="button" class="close" aria-label="' + E("closeAria") + '">×</button></header>' +
    '<ol class="log" aria-live="polite" aria-label="' + E("logAria") + '"></ol>' +
    '<p class="notice">' + E("notice") + '</p>' +
    '<div class="contact-bar"><button type="button" class="contact-open">' + E("contactOpen") + '</button>' +
    '<button type="button" class="book-open" hidden>' + E("bookOpen") + '</button></div>' +
    '<form class="book" hidden novalidate><strong>' + E("bookTitle") + '</strong>' +
    '<label>' + E("bookType") + '<select name="type"></select></label>' +
    '<label>' + E("bookTime") + '<select name="start" required></select></label>' +
    '<label>' + E("name") + '<input name="name" autocomplete="name" maxlength="200" required></label>' +
    '<label>' + E("phone") + '<input name="phone" type="tel" autocomplete="tel" maxlength="40"></label>' +
    '<label>' + E("email") + '<input name="email" type="email" autocomplete="email" maxlength="320"></label>' +
    '<label class="check"><input name="consent" type="checkbox" required> ' + E("bookConsent") + '</label>' +
    '<p class="err" role="alert" hidden></p>' +
    '<div class="row"><button type="button" class="book-cancel">' + E("cancel") + '</button><button type="submit">' + E("bookSubmit") + '</button></div></form>' +
    '<form class="contact" hidden novalidate><strong>' + E("contactTitle") + '</strong>' +
    '<label>' + E("name") + '<input name="name" autocomplete="name" maxlength="200" required></label>' +
    '<label>' + E("email") + '<input name="email" type="email" autocomplete="email" maxlength="320"></label>' +
    '<label>' + E("phone") + '<input name="phone" type="tel" autocomplete="tel" maxlength="40"></label>' +
    '<label>' + E("contactWhen") + '<select name="window"><option value="">' + E("noPreference") + '</option></select></label>' +
    '<label class="check"><input name="consent" type="checkbox" required> ' + E("contactConsent") + '</label>' +
    '<p class="err" role="alert" hidden></p>' +
    '<div class="row"><button type="button" class="contact-cancel">' + E("cancel") + '</button><button type="submit">' + E("send") + '</button></div></form>' +
    '<div class="code-step" role="group" aria-label="' + E("codeTitle") + '" hidden><strong>' + E("codeTitle") + '</strong><p class="hint"></p>' +
    '<label>' + E("codeLabel") + '<input name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}"></label>' +
    '<p class="err" role="alert" hidden></p><p class="ok" role="status" hidden></p>' +
    '<p class="missing" hidden>' + E("codeMissing") + '</p>' +
    '<div class="row"><button type="button" class="code-back">' + E("codeBack") + '</button><button type="button" class="code-resend"></button>' +
    '<button type="button" class="code-submit">' + E("codeSubmit") + '</button></div></div>' +
    '<form><label for="msg" class="sr">' + E("msgLabel") + '</label><textarea id="msg" rows="2" maxlength="' + cfg.maxChars +
    '" placeholder="' + E("placeholder") + '"></textarea><button type="submit">' + E("send") + '</button></form>';
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
  function label(role) { return role === "staff" ? T("staff") : ""; }
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
          var err = new Error(j.message || T("errGeneric")); err.status = r.status; err.code = j.code;
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
    api("GET", "/callback-windows?lang=" + encodeURIComponent(lang)).then(function (j) {
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
    var problem = !body.name ? T("errName") : (!body.email && !body.phone) ? T("errEmailOrPhone")
      : (body.window && !body.phone) ? T("errWindowPhone")
      : !body.consent ? T("errConsent") : "";
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
        var li = bubble("system-ok", T("contactThanks", { name: body.name }));
        manageLink(li, j.manage_url, T("contactManage"));
      })
      .catch(function (x) {
        if (x.code === "verification_required") { pendingContact = body; pendingKind = "contact"; askCode(body.phone); return; }
        codeForm.hidden = true; contactForm.hidden = false;
        err.textContent = x.status === 422 ? T("errCheckContact") : msg(x, "errGeneric"); err.hidden = false;
      });
  }

  // W04: the number is proven with a 6-digit SMS code before the business may call it.
  // The same code step serves «Bliv kontaktet» and the booking form (F-VER1113-04): `pendingKind` says which form
  // the visitor came from and which request is sent again once the number is proven.
  var pendingContact = null, pendingBooking = null, pendingKind = "contact", verification = null, resendTimer = null, checking = false;
  function originForm() { return pendingKind === "booking" ? bookForm : contactForm; }
  function pendingPhone() { return pendingKind === "booking" ? (pendingBooking && pendingBooking.phone) : (pendingContact && pendingContact.phone); }
  var codeErr = codeForm.querySelector(".err"), codeOk = codeForm.querySelector(".ok"), codeHint = codeForm.querySelector(".hint");
  var resend = codeForm.querySelector(".code-resend"), codeInput = codeForm.querySelector("input[name=code]");
  var missing = codeForm.querySelector(".missing"); // «Fik du ikke koden?» once a new code may be asked for
  function codeError(text) { codeErr.textContent = text; codeErr.hidden = false; codeOk.hidden = true; }
  function cooldown(seconds) {
    clearInterval(resendTimer);
    var left = seconds;
    function tick() {
      if (left <= 0) { clearInterval(resendTimer); resendReady(); return; }
      resend.disabled = true; missing.hidden = true; resend.textContent = T("resendIn", { s: left }); left -= 1;
    }
    tick(); resendTimer = setInterval(tick, 1000);
  }
  // The SMS goes out from Dialogbot's worker a moment after the answer; a failed delivery is only logged (Fürster
  // 13/11), so once a new code may be asked for the visitor is told how to get one.
  function resendReady() { resend.disabled = false; resend.textContent = T("resend"); missing.hidden = false; }
  var asking = false; // a double click on «Book»/«Send» answers verification_required twice: ask for one code
  function askCode(phone) {
    var err = originForm().querySelector(".err");
    if (asking) return;
    asking = true;
    ensureConversation()
      .then(function (s) { return api("POST", "/conversations/" + s.id + "/contact/code", { phone: phone }); })
      .then(function (j) {
        verification = j.verification_id;
        contactForm.hidden = true; bookForm.hidden = true; codeForm.hidden = false; codeErr.hidden = true; codeOk.hidden = true;
        codeHint.textContent = T("codeSent", { phone: j.phone_display });
        codeInput.value = ""; codeInput.disabled = false; codeInput.focus();
        cooldown(j.resend_after || 30);
      })
      .finally(function () { asking = false; })
      .catch(function (x) {
        if (!codeForm.hidden) {
          if (x.code === "too_soon") { cooldown(x.retryAfter || 30); codeError(T("tooSoon")); }
          else codeError(msg(x, "codeSendFailed"));
          return;
        }
        err.textContent = x.code === "phone_invalid" ? T("errPhone")
          : x.status === 422 ? T(pendingKind === "booking" ? "errCheckBooking" : "errCheckContact")
          : x.code === "too_soon" ? T("tooSoon")
          : msg(x, "codeSendFailed");
        err.hidden = false;
      });
  }
  resend.addEventListener("click", function () { var p = pendingPhone(); if (p) askCode(p); });
  codeForm.querySelector(".code-back").addEventListener("click", function () {
    clearInterval(resendTimer); codeForm.hidden = true; var f = originForm(); f.hidden = false; f.elements.phone.focus();
  });
  codeInput.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); checkCode(); } });
  codeForm.querySelector(".code-submit").addEventListener("click", checkCode);
  function checkCode() {
    var code = codeInput.value.replace(/\s/g, "");
    if (!/^[0-9]{6}$/.test(code)) { codeError(T("codeFormat")); return; }
    if (checking) return; // a double click checks the code once
    checking = true; codeErr.hidden = true;
    api("POST", "/conversations/" + state.id + "/contact/verify", { verification_id: verification, code: code })
      .finally(function () { checking = false; })
      .then(function () {
        clearInterval(resendTimer);
        codeOk.textContent = T("codeVerified"); codeOk.hidden = false; codeInput.disabled = true; missing.hidden = true;
        if (pendingKind === "booking") sendBooking(pendingBooking); else sendContact(pendingContact);
      })
      .catch(function (x) {
        if (x.code === "code_invalid") {
          codeError(x.attemptsLeft > 0 ? T("codeWrong", { n: x.attemptsLeft }) : T("codeWrongLast"));
          if (!(x.attemptsLeft > 0)) { clearInterval(resendTimer); resendReady(); }
        } else if (x.code === "too_many_attempts") {
          codeError(T("tooMany")); clearInterval(resendTimer); resendReady();
        } else if (x.code === "code_expired") {
          codeError(T("codeExpired")); clearInterval(resendTimer); resendReady();
        } else codeError(msg(x, "errGeneric"));
      });
  }

  /** The customer's secure link (W09/W13) under a confirmation. Built with DOM nodes, only http(s) URLs. */
  function manageLink(li, url, text) {
    if (typeof url !== "string" || !/^https?:\/\//.test(url)) return;
    var a = document.createElement("a");
    a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.className = "manage"; a.textContent = text;
    li.appendChild(document.createElement("br")); li.appendChild(a);
  }

  // Online booking: shown only when the business has it switched on. Danish uses the server's label; another language
  // formats the time itself, in the business's time zone.
  function when(iso, label, tz) {
    if (lang === "da" || !iso || !window.Intl) return label;
    try {
      return new Intl.DateTimeFormat(lang === "no" ? "nb" : lang, { weekday: "long", day: "numeric", month: "long",
        hour: "2-digit", minute: "2-digit", timeZone: tz || undefined }).format(new Date(iso));
    } catch (e) { return label; }
  }
  function fillSlots(j) {
    var types = bookForm.elements.type, starts = bookForm.elements.start;
    if (!types.options.length) j.types.forEach(function (t) { var o = document.createElement("option"); o.value = t.id; o.textContent = t.name; types.appendChild(o); });
    types.value = j.type_id; starts.innerHTML = "";
    if (!j.slots.length) { var o = document.createElement("option"); o.value = ""; o.textContent = T("noSlots"); starts.appendChild(o); }
    j.slots.forEach(function (x) { var o = document.createElement("option"); o.value = x.start; o.textContent = when(x.start, x.label, j.timezone); starts.appendChild(o); });
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
    var problem = !body.start ? T("chooseTime") : !body.name ? T("errName") : (!body.email && !body.phone) ? T("errPhoneOrEmail")
      : !body.consent ? T("errBookConsent") : "";
    if (problem) { err.textContent = problem; err.hidden = false; return; }
    err.hidden = true;
    // A phone number the visitor has not proven in this conversation is answered with `verification_required` → code step
    sendBooking(body);
  });
  function sendBooking(body) {
    var err = bookForm.querySelector(".err");
    ensureConversation()
      .then(function (s) { return api("POST", "/conversations/" + s.id + "/booking", body); })
      .then(function (j) {
        bookForm.hidden = true; codeForm.hidden = true;
        // "pending": the business's calendar could not be read – the time is noted, a staff member confirms it
        var at = when(j.starts_at, j.label, j.timezone);
        var li = bubble("system-ok", j.confirmation === "pending"
          ? T("bookedPending", { name: body.name, when: at }) : T("booked", { name: body.name, when: at }));
        manageLink(li, j.manage_url, T("bookingManage"));
      })
      .catch(function (x) {
        if (x.code === "verification_required") { pendingBooking = body; pendingKind = "booking"; askCode(body.phone); return; }
        codeForm.hidden = true; bookForm.hidden = false;
        err.textContent = x.code === "slot_taken" ? T("slotTaken") : x.status === 422 ? T("errCheckBooking") : msg(x, "errGeneric");
        err.hidden = false;
        if (x.code === "slot_taken") bookForm.elements.type.dispatchEvent(new Event("change"));
      });
  }

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
    var typing = bubble("assistant", T("typing"), "typing");
    send.disabled = true;
    ensureConversation()
      .then(function (s) { return api("POST", "/conversations/" + s.id + "/messages", { text: text }); })
      .then(function (j) {
        typing.remove();
        keepPolling();
        if (j.reply) { seen[j.reply.id] = true; bubble("assistant", j.reply.text); }
        else if (j.waiting_for_staff && !waitingNoted) { waitingNoted = true; bubble("system-ok", T("staffWillReply")); }
      })
      .catch(function (err) {
        typing.remove();
        if (err.status === 401) { state = null; sessionStorage.removeItem(store); }
        bubble("system", msg(err, "sendFailed"));
        if (err.code === "conversation_limit" || err.code === "daily_limit" || err.code === "webchat_unavailable") disable();
      })
      .then(function () { if (!input.disabled) { send.disabled = false; input.focus(); } });
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
})();

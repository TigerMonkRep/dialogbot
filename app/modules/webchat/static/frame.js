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
    '<div class="contact-bar"><button type="button" class="contact-open">Bliv kontaktet af en medarbejder</button></div>' +
    '<form class="contact" hidden novalidate><strong>Bliv kontaktet</strong>' +
    '<label>Navn<input name="name" autocomplete="name" maxlength="200" required></label>' +
    '<label>E-mail<input name="email" type="email" autocomplete="email" maxlength="320"></label>' +
    '<label>Telefon<input name="phone" type="tel" autocomplete="tel" maxlength="40"></label>' +
    '<label class="check"><input name="consent" type="checkbox" required> Virksomheden må kontakte mig om min henvendelse.</label>' +
    '<p class="err" role="alert" hidden></p>' +
    '<div class="row"><button type="button" class="contact-cancel">Annullér</button><button type="submit">Send</button></div></form>' +
    '<form><label for="msg" class="sr">Din besked</label><textarea id="msg" rows="2" maxlength="' + cfg.maxChars +
    '" placeholder="Skriv din besked…"></textarea><button type="submit">Send</button></form>';
  var log = app.querySelector(".log");
  var form = app.querySelector("form:not(.contact)");
  var contactForm = app.querySelector("form.contact");
  var contactBar = app.querySelector(".contact-bar");
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
        if (!r.ok) { var err = new Error(j.message || "Fejl"); err.status = r.status; err.code = j.code; throw err; }
        return j;
      });
    });
  }
  contactBar.querySelector("button").addEventListener("click", function () {
    contactForm.hidden = false; contactBar.hidden = true; contactForm.querySelector("input[name=name]").focus();
  });
  contactForm.querySelector(".contact-cancel").addEventListener("click", function () {
    contactForm.hidden = true; contactBar.hidden = false;
  });
  contactForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var f = contactForm.elements, err = contactForm.querySelector(".err");
    var body = { name: f.name.value.trim(), email: f.email.value.trim() || null, phone: f.phone.value.trim() || null,
                 note: "", consent: f.consent.checked };
    var problem = !body.name ? "Skriv dit navn." : (!body.email && !body.phone) ? "Skriv e-mail eller telefonnummer."
      : !body.consent ? "Sæt flueben, så virksomheden må kontakte dig." : "";
    if (problem) { err.textContent = problem; err.hidden = false; return; }
    err.hidden = true;
    ensureConversation()
      .then(function (s) { return api("POST", "/conversations/" + s.id + "/contact", body); })
      .then(function () {
        contactForm.hidden = true;
        bubble("system-ok", "Tak, " + body.name + "! Virksomheden kontakter dig hurtigst muligt.");
      })
      .catch(function (x) { err.textContent = x.status === 422 ? "Tjek e-mail og telefonnummer." : (x.message || "Det lykkedes ikke. Prøv igen."); err.hidden = false; });
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

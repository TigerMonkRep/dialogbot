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
    '<form><label for="msg" class="sr">Din besked</label><textarea id="msg" rows="2" maxlength="' + cfg.maxChars +
    '" placeholder="Skriv din besked…"></textarea><button type="submit">Send</button></form>';
  var log = app.querySelector(".log");
  var form = app.querySelector("form");
  var input = app.querySelector("textarea");
  var send = form.querySelector("button");
  app.querySelector(".close").addEventListener("click", function () {
    if (window.parent !== window) window.parent.postMessage({ type: "dialogbot:close" }, "*");
  });

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
  function disable(text) {
    input.disabled = true; send.disabled = true;
    if (text) bubble("system", text);
  }

  if (!cfg.available) { bubble("system", cfg.unavailable); disable(); return; }
  bubble("assistant", cfg.greeting);
  if (state) {
    api("GET", "/conversations/" + state.id + "/messages").then(function (j) {
      j.messages.forEach(function (m) { bubble(m.role, m.text); });
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
      .then(function (j) { typing.remove(); bubble("assistant", j.reply.text); })
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

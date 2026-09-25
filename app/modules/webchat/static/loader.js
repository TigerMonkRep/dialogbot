/* Dialogbot web widget loader.
 * <script src="https://<api>/api/v1/public/webchat/loader.js" data-dialogbot-key="wk_…" async></script>
 * Shows a launcher only when the workspace allows this site and the chat is available.
 * The chat runs in an iframe on the Dialogbot origin; this page never sees the conversation token. */
(function () {
  "use strict";
  var script = document.currentScript;
  if (!script || window.__dialogbotWidget) return;
  window.__dialogbotWidget = true;
  var key = script.getAttribute("data-dialogbot-key") || "";
  if (!/^wk_[A-Za-z0-9_-]{8,}$/.test(key)) return;
  var api = new URL(script.src).origin;
  var base = api + "/api/v1/public/webchat/" + encodeURIComponent(key);

  fetch(base + "/status", { credentials: "omit", mode: "cors" })
    .then(function (r) { return r.ok ? r.json() : { available: false }; })
    .then(function (s) { if (s && s.available) mount(); })
    .catch(function () { /* not allowed on this site or offline: show nothing */ });

  function mount() {
    var host = document.createElement("div");
    host.setAttribute("data-dialogbot", "");
    host.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483000;";
    var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
    var style = document.createElement("style");
    style.textContent =
      ".btn{width:56px;height:56px;border-radius:28px;border:0;background:#00362d;color:#d6ec85;cursor:pointer;" +
      "box-shadow:0 6px 20px rgba(0,54,45,.3);display:flex;align-items:center;justify-content:center;margin-left:auto}" +
      ".btn:focus-visible{outline:3px solid #546508;outline-offset:3px}" +
      ".panel{display:none;width:min(380px,calc(100vw - 32px));height:min(560px,calc(100vh - 104px));margin-bottom:12px;" +
      "border:0;border-radius:16px;box-shadow:0 12px 40px rgba(0,54,45,.25);background:#fff}" +
      ".open .panel{display:block}";
    var wrap = document.createElement("div");
    var frame = document.createElement("iframe");
    frame.className = "panel";
    frame.title = "Chat med virksomhedens digitale assistent";
    frame.setAttribute("allow", "");
    frame.setAttribute("referrerpolicy", "strict-origin");
    var btn = document.createElement("button");
    btn.className = "btn";
    btn.type = "button";
    btn.setAttribute("aria-label", "Åbn chat");
    btn.setAttribute("aria-expanded", "false");
    btn.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M20 2H4a2 2 0 0 0-2 2v18l4-4h14a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2Z"/></svg>';
    function setOpen(open) {
      if (open && !frame.src) frame.src = base + "/frame";
      wrap.className = open ? "open" : "";
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.setAttribute("aria-label", open ? "Luk chat" : "Åbn chat");
      if (open) frame.focus(); else btn.focus();
    }
    btn.addEventListener("click", function () { setOpen(wrap.className !== "open"); });
    window.addEventListener("message", function (e) {
      if (e.origin === api && e.source === frame.contentWindow && e.data && e.data.type === "dialogbot:close") setOpen(false);
    });
    wrap.appendChild(frame);
    wrap.appendChild(btn);
    root.appendChild(style);
    root.appendChild(wrap);
    document.body.appendChild(host);
  }
})();

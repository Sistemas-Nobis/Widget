/*
 * widget-auth.js — gate de sesión del widget embebido (cross-site, CHIPS).
 *
 * Config esperada en window.WIDGET_AUTH:
 *   { enabled, origin, statusUrl, loginUrl, exchangeUrl, handoffUrl, pollMs, role }
 *   role: "atencion" (interstitial con botón) | "bloqueado" (overlay que tapa la app)
 *
 * Flujo: botón -> popup top-level login MSAL -> callback emite handoff por postMessage
 *        -> este iframe hace exchange (materializa su cookie en su partición) -> reload.
 * Sincronización entre pestañas del mismo top-level: BroadcastChannel + polling.
 */
(function () {
  "use strict";
  var CFG = window.WIDGET_AUTH || {};
  if (!CFG.enabled) return;                         // gate dormido -> no tocar nada

  var POLL_MS = CFG.pollMs || 5000;
  var ORIGIN = CFG.origin;
  var ROLE = CFG.role || "bloqueado";
  var channelNonce = null;
  var pollTimer = null;
  var bc = null;
  try { bc = new BroadcastChannel("widget-auth"); } catch (e) { bc = null; }

  // ------------------------------------------------------------------ helpers
  function isAuthed() {
    return fetch(CFG.statusUrl, { credentials: "include", cache: "no-store",
                                  headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : { authenticated: false }; })
      .then(function (s) { return !!s.authenticated; })
      .catch(function () { return false; });
  }

  function overlayVisible() { return !!document.getElementById("widget-auth-overlay"); }

  function finishAuthed() {
    if (bc) { try { bc.postMessage({ type: "authenticated" }); } catch (e) {} }
    window.location.reload();
  }

  // ---------------------------------------------------------------- exchange
  function exchange(handoff) {
    return fetch(CFG.exchangeUrl, {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ handoff: handoff, ch: channelNonce })
    }).catch(function () {});
  }

  function onLoginSignal(handoff) {
    if (!handoff) return;
    exchange(handoff).then(function () {
      isAuthed().then(function (ok) { if (ok) finishAuthed(); });
    });
  }

  // -------------------------------------------------------------------- login
  function startLogin() {
    channelNonce = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
                                                        : String(Date.now()) + Math.round(1e9 * (0.5));
    var w = 520, h = 640;
    var left = (screen.width - w) / 2, top = (screen.height - h) / 2;
    window.open(CFG.loginUrl + "?ch=" + encodeURIComponent(channelNonce),
                "widget_login", "width=" + w + ",height=" + h + ",left=" + left + ",top=" + top);
    setTimeout(pollHandoff, 2000);                  // fallback opener cortado
  }

  var handoffTries = 0;
  function pollHandoff() {
    if (!channelNonce || handoffTries > 15) return;
    handoffTries++;
    fetch(CFG.handoffUrl + "?ch=" + encodeURIComponent(channelNonce), { credentials: "include", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) { if (d && d.handoff) { onLoginSignal(d.handoff); } else { setTimeout(pollHandoff, 2000); } })
      .catch(function () { setTimeout(pollHandoff, 2000); });
  }

  // ------------------------------------------------------------------ overlay
  function mountOverlay() {
    if (overlayVisible()) return;
    var esAtencion = (ROLE === "atencion");
    var ov = document.createElement("div");
    ov.id = "widget-auth-overlay";
    ov.setAttribute("style", [
      "position:fixed", "inset:0", "z-index:2147483647",
      "background:" + (esAtencion ? "#ffffff" : "#0e8c13"),
      "color:" + (esAtencion ? "#0e8c13" : "#ffffff"),
      "display:flex", "flex-direction:column", "align-items:center", "justify-content:center",
      "font-family:Arial,sans-serif", "text-align:center", "gap:16px", "padding:20px"
    ].join(";"));
    var titulo = esAtencion ? "Iniciá sesión para usar el widget" : "Esperando inicio de sesión...";
    ov.innerHTML =
      '<div style="font-size:16px;font-weight:bold;">' + titulo + '</div>' +
      (esAtencion ? '' : '<div style="font-size:13px;opacity:.85;">Esta sección se desbloqueará automáticamente.</div>') +
      '<button id="widget-auth-login-btn" style="padding:10px 22px;border:0;border-radius:6px;cursor:pointer;' +
        'background:' + (esAtencion ? "#0e8c13" : "#ffffff") + ';color:' + (esAtencion ? "#ffffff" : "#0e8c13") + ';' +
        'font-weight:bold;font-size:14px;">Iniciar sesión</button>';
    document.body.appendChild(ov);
    document.getElementById("widget-auth-login-btn").addEventListener("click", startLogin);
  }

  function unmountOverlay() {
    var ov = document.getElementById("widget-auth-overlay");
    if (ov) ov.parentNode.removeChild(ov);
  }

  // -------------------------------------------------------------- suscripciones
  window.addEventListener("message", function (ev) {
    if (ev.origin !== ORIGIN) return;               // solo mensajes de nuestro origen
    if (ev.data && ev.data.type === "widget-login-success" && ev.data.handoff) {
      onLoginSignal(ev.data.handoff);
    }
  });

  if (bc) {
    bc.onmessage = function (ev) {
      if (!ev.data) return;
      if (ev.data.type === "auth-changed" || ev.data.type === "authenticated") {
        isAuthed().then(function (ok) { if (ok) window.location.reload(); });
      }
    };
  }

  // -------------------------------------------------------------- polling ciclo
  function startPolling(authedInicial) {
    if (pollTimer) return;
    var authed = authedInicial;
    pollTimer = setInterval(function () {
      isAuthed().then(function (ok) {
        if (ok && !authed) { window.location.reload(); }        // se logueó en otra pestaña
        else if (!ok && authed) { authed = false; mountOverlay(); } // expiró / logout
      });
    }, POLL_MS);
  }

  // ------------------------------------------------------------------ bootstrap
  function init() {
    isAuthed().then(function (ok) {
      if (!ok) { mountOverlay(); startPolling(false); }
      else { unmountOverlay(); startPolling(true); }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

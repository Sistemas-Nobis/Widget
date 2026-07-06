/*
 * widget-auth.js — gate de sesión del widget embebido (cross-site, CHIPS).
 *
 * Config en window.WIDGET_AUTH:
 *   { enabled, origin, statusUrl, loginUrl, exchangeUrl, handoffUrl, pollMs, role }
 *   role: "atencion" | "bloqueado"
 *
 * Flujo: botón -> popup top-level login MSAL -> callback emite un handoff por postMessage
 *        -> este contexto hace exchange (materializa su cookie) -> recarga.
 */
(function () {
  "use strict";
  var CFG = window.WIDGET_AUTH || {};
  function log() { try { console.info.apply(console, ["[widget-auth]"].concat([].slice.call(arguments))); } catch (e) {} }

  if (!CFG.enabled) { log("gate deshabilitado (WIDGET_AUTH_ENABLED=False)"); return; }

  var POLL_MS = CFG.pollMs || 5000;
  var ORIGIN = CFG.origin;
  var ROLE = CFG.role || "bloqueado";
  var channelNonce = null;
  var pollTimer = null;
  var loggingIn = false;
  var btnEl = null;
  var bc = null;
  try { bc = new BroadcastChannel("widget-auth"); } catch (e) { bc = null; }

  // ---------------------------------------------------------------- estilos
  function injectStyles() {
    if (document.getElementById("wa-styles")) return;
    var css =
      "#wa-overlay{position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;justify-content:center;" +
        "padding:18px;background:linear-gradient(135deg,#0e8c13 0%,#0a6b0f 100%);font-family:'Segoe UI',Roboto,Arial,sans-serif;}" +
      "#wa-card{width:100%;max-width:320px;background:#fff;border-radius:16px;padding:28px 22px;text-align:center;" +
        "box-shadow:0 18px 45px rgba(0,0,0,.28);animation:wa-in .25s ease-out;}" +
      "@keyframes wa-in{from{opacity:0;transform:translateY(8px) scale(.98)}to{opacity:1;transform:none}}" +
      ".wa-badge{width:56px;height:56px;border-radius:50%;background:#eafbe9;display:flex;align-items:center;justify-content:center;margin:0 auto 14px;}" +
      "#wa-title{font-size:17px;font-weight:700;color:#0e8c13;margin:0 0 6px;}" +
      "#wa-sub{font-size:13px;color:#666;margin:0 0 20px;line-height:1.4;}" +
      "#wa-btn{width:100%;display:flex;align-items:center;justify-content:center;gap:10px;padding:11px 14px;border:1px solid #d0d0d0;" +
        "border-radius:8px;background:#fff;color:#3b3b3b;font-size:14px;font-weight:600;cursor:pointer;transition:background .15s,box-shadow .15s;}" +
      "#wa-btn:hover:not(:disabled){background:#f5f5f5;box-shadow:0 2px 8px rgba(0,0,0,.08);}" +
      "#wa-btn:disabled{cursor:default;opacity:.85;}" +
      ".wa-spin{width:16px;height:16px;border:2px solid rgba(14,140,19,.25);border-top-color:#0e8c13;border-radius:50%;" +
        "display:inline-block;animation:wa-rot .7s linear infinite;}" +
      "@keyframes wa-rot{to{transform:rotate(360deg)}}" +
      ".wa-hint{margin-top:14px;font-size:11px;color:#9aa;}";
    var st = document.createElement("style");
    st.id = "wa-styles"; st.textContent = css;
    document.head.appendChild(st);
  }

  var MS_ICON =
    '<svg width="18" height="18" viewBox="0 0 21 21" aria-hidden="true">' +
    '<rect x="1" y="1" width="9" height="9" fill="#f35325"/><rect x="11" y="1" width="9" height="9" fill="#81bc06"/>' +
    '<rect x="1" y="11" width="9" height="9" fill="#05a6f0"/><rect x="11" y="11" width="9" height="9" fill="#ffba08"/></svg>';

  function btnIdle() { return MS_ICON + '<span>Iniciar sesión con Microsoft</span>'; }
  function btnLoading() { return '<span class="wa-spin"></span><span>Iniciando sesión…</span>'; }

  // ---------------------------------------------------------------- overlay
  function mountOverlay() {
    if (document.getElementById("wa-overlay")) return;
    injectStyles();
    var esAtencion = (ROLE === "atencion");
    var titulo = esAtencion ? "Iniciá sesión para continuar" : "Esperando inicio de sesión";
    var sub = esAtencion
      ? "Necesitás autenticarte con tu cuenta de Nobis para usar el widget."
      : "Esta sección se desbloquea automáticamente al iniciar sesión.";
    var ov = document.createElement("div");
    ov.id = "wa-overlay";
    ov.innerHTML =
      '<div id="wa-card">' +
        '<div class="wa-badge">' + MS_ICON + '</div>' +
        '<h2 id="wa-title">' + titulo + '</h2>' +
        '<p id="wa-sub">' + sub + '</p>' +
        '<button id="wa-btn" type="button">' + btnIdle() + '</button>' +
        '<div class="wa-hint">Se abrirá una ventana de Microsoft.</div>' +
      '</div>';
    document.body.appendChild(ov);
    btnEl = document.getElementById("wa-btn");
    btnEl.addEventListener("click", startLogin);
    if (loggingIn) setButtonLoading(true);   // conservar estado si se re-monta
  }

  function unmountOverlay() {
    var ov = document.getElementById("wa-overlay");
    if (ov && ov.parentNode) ov.parentNode.removeChild(ov);
    btnEl = null;
  }

  function setButtonLoading(on) {
    if (!btnEl) return;
    btnEl.disabled = on;
    btnEl.innerHTML = on ? btnLoading() : btnIdle();
  }

  function resetLogin() {
    loggingIn = false;
    setButtonLoading(false);
  }

  // ------------------------------------------------------------------ auth
  function isAuthed() {
    return fetch(CFG.statusUrl, { credentials: "include", cache: "no-store", headers: { "Accept": "application/json" } })
      .then(function (r) { return r.ok ? r.json() : { authenticated: false }; })
      .then(function (s) { return !!s.authenticated; })
      .catch(function () { return false; });
  }

  function exchange(handoff) {
    log("exchange…");
    return fetch(CFG.exchangeUrl, {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ handoff: handoff, ch: channelNonce })
    }).then(function (r) { return r.ok ? r.json() : null; })
      .catch(function (e) { log("exchange error", e); return null; });
  }

  function finishAuthed() {
    log("autenticado -> recargando");
    if (bc) { try { bc.postMessage({ type: "authenticated" }); } catch (e) {} }
    window.location.reload();
  }

  function onLoginSignal(handoff) {
    if (!handoff) return;
    log("handoff recibido");
    exchange(handoff).then(function (res) {
      if (res && res.authenticated) { finishAuthed(); return; }
      // Si el exchange no confirmó (ej. handoff ya consumido por otra vía), verificar sesión.
      isAuthed().then(function (ok) {
        if (ok) finishAuthed();
        else { log("exchange sin sesión", res); resetLogin(); }
      });
    });
  }

  // -------------------------------------------------------------------- login
  function newNonce() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "n" + Date.now() + "-" + Math.round(1e9 * parseFloat("0." + (Date.now() % 997)));
  }

  function startLogin() {
    if (loggingIn) { log("login ya en curso — click ignorado"); return; }
    loggingIn = true;
    setButtonLoading(true);
    channelNonce = newNonce();
    log("abriendo popup de login");
    var w = 520, h = 640;
    var left = Math.max(0, (screen.width - w) / 2), top = Math.max(0, (screen.height - h) / 2);
    var popup = window.open(CFG.loginUrl + "?ch=" + encodeURIComponent(channelNonce),
                            "widget_login", "width=" + w + ",height=" + h + ",left=" + left + ",top=" + top);
    if (!popup) {
      log("popup BLOQUEADO por el navegador");
      alert("El navegador bloqueó la ventana de inicio de sesión. Permití las ventanas emergentes para este sitio.");
      resetLogin();
      return;
    }
    handoffTries = 0;
    setTimeout(pollHandoff, 2000);           // fallback si el postMessage no llega
    watchPopup(popup);
  }

  function watchPopup(popup) {
    var watch = setInterval(function () {
      if (!popup || popup.closed) {
        clearInterval(watch);
        // margen para que el handoff/exchange terminen; si no autenticó, reactivar el botón.
        setTimeout(function () {
          isAuthed().then(function (ok) { if (!ok) { log("popup cerrado sin sesión"); resetLogin(); } });
        }, 2500);
      }
    }, 600);
  }

  var handoffTries = 0;
  function pollHandoff() {
    if (!channelNonce || !loggingIn || handoffTries > 15) return;
    handoffTries++;
    fetch(CFG.handoffUrl + "?ch=" + encodeURIComponent(channelNonce), { credentials: "include", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) { if (d && d.handoff) { onLoginSignal(d.handoff); } else { setTimeout(pollHandoff, 2000); } })
      .catch(function () { setTimeout(pollHandoff, 2000); });
  }

  // -------------------------------------------------------------- suscripciones
  window.addEventListener("message", function (ev) {
    if (ev.origin !== ORIGIN) return;
    if (ev.data && ev.data.type === "widget-login-success" && ev.data.handoff) {
      log("postMessage de éxito recibido");
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
        if (ok && !authed) { authed = true; finishAuthed(); }
        else if (!ok && authed) { authed = false; mountOverlay(); }
      });
    }, POLL_MS);
  }

  // ------------------------------------------------------------------ bootstrap
  function init() {
    isAuthed().then(function (ok) {
      log("estado inicial:", ok ? "autenticado" : "sin sesión");
      if (!ok) { mountOverlay(); startPolling(false); }
      else { unmountOverlay(); startPolling(true); }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

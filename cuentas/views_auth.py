"""
Flujo de autenticación MSAL para el widget embebido como iframe cross-site.

Piezas:
  login_start  (popup top-level)  -> arranca el auth-code flow
  callback     (popup top-level)  -> valida, crea identidad + AuthHandoff, cierra el popup
  exchange     (iframe, POST)     -> canjea el handoff y materializa la sesión EN la partición del iframe
  auth_status  (GET)              -> {authenticated, user} desde la sesión
  handoff_poll (GET)              -> fallback opener-severed: recupera el handoff por channel_nonce
  logout       (POST)             -> session.flush() local
"""
import json
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import AuthHandoff
from .msal_utils import construir_app, extraer_grupos
from .permisos import calcular_es_superadmin


def _widget_origin() -> str:
    p = urlparse(settings.MSAL_REDIRECT_URI)
    return f"{p.scheme}://{p.netloc}"


def _auth_configurada() -> bool:
    return bool(settings.MSAL_CLIENT_ID and settings.MSAL_CLIENT_SECRET and settings.MSAL_AUTHORITY)


def _set_identidad(session, *, upn, oid, nombre, grupos, es_superadmin):
    session["upn"] = upn
    session["oid"] = oid
    session["nombre"] = nombre
    session["grupos"] = grupos
    session["es_superadmin"] = es_superadmin


@never_cache
def login_start(request):
    """Corre top-level (popup o pestaña). Guarda el flow en la sesión del contexto top-level."""
    if not _auth_configurada():
        return HttpResponse("Autenticación no configurada (faltan credenciales MSAL).", status=503)
    app = construir_app()
    flow = app.initiate_auth_code_flow(
        settings.MSAL_SCOPES,
        redirect_uri=settings.MSAL_REDIRECT_URI,   # string PÚBLICO fijo; nunca build_absolute_uri
    )
    request.session["auth_flow"] = flow
    request.session["auth_ch"] = request.GET.get("ch", "")
    request.session["auth_next"] = request.GET.get("next", "")
    return redirect(flow["auth_uri"])


@never_cache
def callback(request):
    """Redirect URI de Azure. Corre top-level en el popup."""
    flow = request.session.pop("auth_flow", None)
    if not flow:
        return HttpResponse("Sesión de login expirada. Cerrá esta ventana y reintentá.", status=400)

    app = construir_app()
    result = app.acquire_token_by_auth_code_flow(
        flow, {k: v for k, v in request.GET.items()}
    )
    if "error" in result:
        return HttpResponse(
            f"Error de autenticación: {result.get('error_description', result['error'])}",
            status=401,
        )

    claims = result.get("id_token_claims", {})
    upn = claims.get("preferred_username") or claims.get("upn") or ""
    oid = claims.get("oid") or claims.get("sub") or ""
    nombre = claims.get("name") or ""
    grupos = extraer_grupos(claims)
    es_super = calcular_es_superadmin(upn, grupos)

    # Identidad en la sesión top-level del popup (habilita SSO para otros top-levels).
    _set_identidad(request.session, upn=upn, oid=oid, nombre=nombre,
                   grupos=grupos, es_superadmin=es_super)

    ch = request.session.pop("auth_ch", "")
    next_url = request.session.pop("auth_next", "")

    # Flujo superadmin/top-level: sin iframe, la cookie first-party ya sirve.
    if next_url:
        return redirect(next_url)

    # Flujo iframe: emitir un handoff de un solo uso y cerrar el popup.
    handoff = AuthHandoff.objects.create(
        channel_nonce=ch,
        upn=upn, oid=oid, nombre=nombre,
        grupos=grupos, es_superadmin=es_super,
        expires_at=timezone.now() + timedelta(seconds=60),
    )
    return render(request, "cuentas/auth_close.html", {
        "handoff": str(handoff.token),
        "target_origin": _widget_origin(),
    })


@csrf_exempt
@require_POST
def exchange(request):
    """
    El iframe canjea el handoff. Esta request NACE en la partición del iframe,
    así el Set-Cookie de sesión cae en la partición correcta (CHIPS).
    Anti-forgery: el handoff es un UUID de alta entropía, single-use, TTL 60s.
    """
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse({"error": "body_invalido"}, status=400)

    token = (data.get("handoff") or "").strip()
    if not token:
        return JsonResponse({"error": "falta_handoff"}, status=400)

    now = timezone.now()
    AuthHandoff.objects.filter(expires_at__lt=now).delete()  # barrido lazy

    # Consumo atómico single-use: UPDATE ... WHERE consumed_at IS NULL
    consumido = AuthHandoff.objects.filter(
        token=token, consumed_at__isnull=True, expires_at__gte=now
    ).update(consumed_at=now)
    if not consumido:
        return JsonResponse({"error": "handoff_invalido"}, status=400)

    h = AuthHandoff.objects.get(token=token)
    # No se usa cycle_key(): en dev el popup y la pestaña comparten la misma cookie
    # (mismo origen, sin partición) y rotar/borrar la clave pisaría la sesión que otros
    # contextos están usando. El handoff single-use + validación de origin ya mitigan fixation.
    _set_identidad(request.session, upn=h.upn, oid=h.oid, nombre=h.nombre,
                   grupos=h.grupos, es_superadmin=h.es_superadmin)
    request.session.modified = True
    return JsonResponse({"authenticated": True, "user": {"upn": h.upn, "nombre": h.nombre}})


@never_cache
@require_GET
def auth_status(request):
    upn = request.session.get("upn")
    return JsonResponse({
        "authenticated": bool(upn),
        "user": {"upn": upn, "nombre": request.session.get("nombre")} if upn else None,
    })


@never_cache
@require_GET
def handoff_poll(request):
    """Fallback cuando el postMessage no llegó (opener cortado). Devuelve el token por nonce."""
    ch = request.GET.get("ch", "")
    if not ch:
        return JsonResponse({"handoff": None})
    now = timezone.now()
    h = (AuthHandoff.objects
         .filter(channel_nonce=ch, consumed_at__isnull=True, expires_at__gte=now)
         .order_by("-created_at").first())
    return JsonResponse({"handoff": str(h.token) if h else None})


@never_cache
def logout(request):
    request.session.flush()
    if request.method == "POST":
        return JsonResponse({"ok": True})
    return HttpResponse("Sesión cerrada.")


@never_cache
@require_GET
def whoami(request):
    """Diagnóstico (solo DEBUG): qué identidad/grupos/permisos ve el gate para esta sesión."""
    if not settings.DEBUG:
        raise Http404()
    from .permisos import usuario_puede
    from .recursos import RECURSO_KEYS
    permisos = {k: usuario_puede(request, k) for k in sorted(RECURSO_KEYS)}
    return JsonResponse({
        "upn": request.session.get("upn"),
        "nombre": request.session.get("nombre"),
        "oid": request.session.get("oid"),
        "grupos": request.session.get("grupos"),
        "es_superadmin": request.session.get("es_superadmin"),
        "permisos": permisos,
    }, json_dumps_params={"indent": 2, "ensure_ascii": False})


@never_cache
def dev_login(request):
    """
    SOLO PARA PRUEBAS LOCALES. Setea una sesión sin pasar por Azure AD.
    Gated estrictamente: 404 salvo DEBUG=True y WIDGET_CROSS_SITE=False.
    Uso: /auth/dev_login?upn=juan@nobis.com.ar&grupos=<oid1>,<oid2>&super=0&next=/atencion/12345678/
    """
    if not settings.DEBUG or getattr(settings, "WIDGET_CROSS_SITE", False):
        raise Http404()
    upn = request.GET.get("upn", "dev@nobis.com.ar")
    nombre = request.GET.get("nombre", upn)
    grupos = [g.strip() for g in request.GET.get("grupos", "").split(",") if g.strip()]
    es_super = request.GET.get("super", "") in ("1", "true", "True") or \
        calcular_es_superadmin(upn, grupos)
    request.session.cycle_key()
    _set_identidad(request.session, upn=upn, oid=f"dev-{upn}", nombre=nombre,
                   grupos=grupos, es_superadmin=es_super)
    return redirect(request.GET.get("next", "/"))

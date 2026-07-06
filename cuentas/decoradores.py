"""
Decoradores de gate (autenticación + autorización RBAC).

- Con settings.WIDGET_AUTH_ENABLED == False, TODOS pasan de largo (deploy dormido / rollback).
- iframe  -> devuelve HTML (401 pantalla de login / 403 sin acceso). NO ejecuta la vista si falta permiso.
- json    -> devuelve JSON (401 / 403) para no romper los response.json() del frontend.
- 401 = no autenticado ; 403 = autenticado pero sin permiso.
"""
from functools import wraps

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render

from .permisos import esta_autenticado, usuario_puede, es_superadmin


def _auth_activa() -> bool:
    return getattr(settings, "WIDGET_AUTH_ENABLED", False)


# Vistas intercambiables para el botón "ir a una vista accesible" en la pantalla 403.
# Mesa NO participa (no tiene contraparte natural) -> sin botón.
_PARES_VISTA = {
    "vista.retencion": ("vista.atencion", "atencion", "Atención"),
    "vista.atencion": ("vista.retencion", "retencion", "Retención"),
}


def _vista_alternativa(request, recurso_key, kwargs):
    """Devuelve {url,label} de una vista accesible equivalente, o None (sin botón)."""
    par = _PARES_VISTA.get(recurso_key)
    if not par:
        return None                                  # mesa u otra: sin botón
    recurso_alt, path_alt, label_alt = par
    if not usuario_puede(request, recurso_alt):
        return None                                  # no tiene la contraparte: sin botón
    dni = kwargs.get("dni")
    if not dni:
        return None                                  # sin DNI no se puede armar la URL
    prefix = getattr(settings, "WIDGET_URL_PREFIX", "")
    return {"url": f"{prefix}/{path_alt}/{dni}/", "label": label_alt}


def requiere_permiso_iframe(recurso_key):
    """Para las CBV (vistas GET que renderizan el iframe)."""
    def deco(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not _auth_activa():
                return view_func(request, *args, **kwargs)
            if not esta_autenticado(request):
                role = "atencion" if recurso_key == "vista.atencion" else "bloqueado"
                return render(request, "cuentas/bloqueo_login.html",
                              {"recurso": recurso_key, "role": role}, status=401)
            if not usuario_puede(request, recurso_key):
                return render(request, "cuentas/sin_acceso.html",
                              {"recurso": recurso_key,
                               "alternativa": _vista_alternativa(request, recurso_key, kwargs)},
                              status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return deco


def requiere_permiso_json(recurso_key):
    """Para los endpoints POST (@csrf_exempt) y los AJAX de lectura."""
    def deco(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not _auth_activa():
                return view_func(request, *args, **kwargs)
            if not esta_autenticado(request):
                return JsonResponse({"error": "no_autenticado"}, status=401)
            if not usuario_puede(request, recurso_key):
                return JsonResponse({"error": "sin_permiso", "recurso": recurso_key}, status=403)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return deco


def superadmin_required_page(view_func):
    """Pantalla de administración (top-level, first-party)."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not _auth_activa():
            return view_func(request, *args, **kwargs)
        if not esta_autenticado(request):
            from django.shortcuts import redirect
            from urllib.parse import quote
            prefix = getattr(settings, "WIDGET_URL_PREFIX", "")
            next_path = quote(f"{prefix}{request.path}")
            return redirect(f"{prefix}/auth/login_start?next={next_path}")
        if not es_superadmin(request):
            return render(request, "cuentas/gestion_denegado.html", status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped


def superadmin_required_json(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not _auth_activa():
            return view_func(request, *args, **kwargs)
        if not esta_autenticado(request):
            return JsonResponse({"error": "no_autenticado"}, status=401)
        if not es_superadmin(request):
            return JsonResponse({"error": "forbidden"}, status=403)
        return view_func(request, *args, **kwargs)
    return _wrapped

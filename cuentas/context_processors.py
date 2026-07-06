"""
Expone a TODOS los templates la config que consume widget-auth.js, sin tocar cada vista.

Uso en el template (antes de </body>):

    {% load static %}
    <script>window.WIDGET_AUTH = Object.assign({{ widget_auth_json|safe }}, {role: "atencion"});</script>
    <script src="{% static 'afiliados/js/widget-auth.js' %}"></script>
"""
import json
from urllib.parse import urlparse

from django.conf import settings


def widget_auth(request):
    p = getattr(settings, "WIDGET_URL_PREFIX", "")
    cfg = {
        "enabled": getattr(settings, "WIDGET_AUTH_ENABLED", False),
        "origin": _origin(),
        "statusUrl": f"{p}/auth/status",
        "loginUrl": f"{p}/auth/login_start",
        "exchangeUrl": f"{p}/auth/exchange",
        "handoffUrl": f"{p}/auth/handoff",
        "pollMs": 5000,
    }
    return {
        "widget_auth_json": json.dumps(cfg),
        "widget_perms": _permisos(request),
    }


def _permisos(request):
    """
    Permisos (vistas + acciones) para ocultar navegación/botones en los templates.
    Clave = nombre corto sin prefijo: widget_perms.retencion, widget_perms.crear_expediente, etc.
    Con el gate apagado (o sin sesión) devuelve todo True (comportamiento previo intacto).
    """
    from .permisos import usuario_puede, esta_autenticado
    from .recursos import RECURSO_KEYS
    activo = getattr(settings, "WIDGET_AUTH_ENABLED", False) and esta_autenticado(request)
    perms = {}
    for key in RECURSO_KEYS:
        short = key.split(".", 1)[1]                 # "vista.atencion" -> "atencion"
        perms[short] = usuario_puede(request, key) if activo else True
    return perms


def _origin():
    p = urlparse(settings.MSAL_REDIRECT_URI)
    if p.scheme and p.netloc:
        return f"{p.scheme}://{p.netloc}"
    return ""

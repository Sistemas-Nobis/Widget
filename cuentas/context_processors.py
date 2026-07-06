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
    return {"widget_auth_json": json.dumps(cfg)}


def _origin():
    p = urlparse(settings.MSAL_REDIRECT_URI)
    if p.scheme and p.netloc:
        return f"{p.scheme}://{p.netloc}"
    return ""

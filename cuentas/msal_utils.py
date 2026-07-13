"""
Helpers de MSAL: construcción de la app confidencial, y resolución de los grupos
de Entra del usuario (claim 'groups' con fallback a Graph ante overage >200 grupos).
"""
import logging

import msal
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_GRAPH = "https://graph.microsoft.com"


class _SesionConTimeout(requests.Session):
    """
    requests.Session que aplica settings.REQUESTS_TIMEOUT por defecto a TODA llamada.

    Se pasa como http_client a MSAL para que sus requests internas (token endpoint de
    login.microsoftonline.com, discovery de metadata) tampoco puedan colgar un hilo WSGI
    indefinidamente si Azure deja de responder.
    """
    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", settings.REQUESTS_TIMEOUT)
        return super().request(*args, **kwargs)


def construir_app():
    """ConfidentialClientApplication a partir de settings/.env."""
    return msal.ConfidentialClientApplication(
        client_id=settings.MSAL_CLIENT_ID,
        authority=settings.MSAL_AUTHORITY,
        client_credential=settings.MSAL_CLIENT_SECRET,
        http_client=_SesionConTimeout(),   # timeout en las llamadas internas de MSAL
    )


def _graph_app_token():
    """
    Token app-only (client credentials) para consultar Graph en el fallback de overage.
    Requiere permiso de APLICACIÓN GroupMember.Read.All (o Directory.Read.All) + consentimiento admin.
    """
    try:
        # construir_app() hace red (discovery del tenant) -> dentro del try, así un
        # timeout de Azure devuelve None (deny) en vez de romper el callback.
        app = construir_app()
        result = app.acquire_token_for_client(scopes=[f"{_GRAPH}/.default"])
    except requests.RequestException as e:
        logger.error("Timeout/error de red obteniendo token app-only de Graph: %s", e)
        return None
    if "access_token" in result:
        return result["access_token"]
    logger.error("No se pudo obtener token app-only de Graph: %s", result.get("error_description"))
    return None


def _grupos_por_graph(oid: str):
    """POST /users/{oid}/getMemberGroups -> lista de oids de grupos del usuario (vía Graph app-only)."""
    token = _graph_app_token()
    if not token or not oid:
        logger.warning("Graph: sin token app-only o sin oid (oid=%s, token=%s)", oid, bool(token))
        return []
    try:
        r = requests.post(f"{_GRAPH}/v1.0/users/{oid}/getMemberGroups", timeout=settings.REQUESTS_TIMEOUT,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"securityEnabledOnly": False})   # todos los grupos, no solo security-enabled
        if r.status_code == 200:
            return r.json().get("value", [])
        logger.error("getMemberGroups fallo %s: %s", r.status_code, r.text[:400])
    except requests.RequestException as e:
        logger.error("getMemberGroups excepción: %s", e)
    return []


def extraer_grupos(claims: dict) -> list:
    """
    Devuelve la lista de oids de grupos del usuario.
    - Si el token trae el claim 'groups', se usa directo.
    - Si NO lo trae (claim no configurado u overage >200 grupos), se resuelve por Graph
      (getMemberGroups app-only). Requiere permiso de APLICACIÓN GroupMember.Read.All o
      Directory.Read.All + consentimiento de admin en la App Registration.
    """
    grupos_claim = claims.get("groups")
    if grupos_claim:
        return grupos_claim
    oid = claims.get("oid") or claims.get("sub")
    grupos = _grupos_por_graph(oid)
    if not grupos:
        logger.warning("Sin grupos en el token y Graph no devolvió grupos para oid=%s -> deny", oid)
    return grupos

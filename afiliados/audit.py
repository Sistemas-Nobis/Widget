"""
Helper de auditoría. registrar() nunca debe tumbar la request (todo va en try/except).
La identidad se lee de request.session (puesta por el flujo MSAL de la app cuentas).
"""
import logging

logger = logging.getLogger(__name__)


def identidad_de(request):
    s = getattr(request, "session", {}) or {}
    return {
        "upn": s.get("upn") or "",
        "oid": s.get("oid") or "",
        "nombre": s.get("nombre") or "",
    }


def etiqueta_usuario(request):
    """String legible para anexar en campos de texto de sistemas externos (observaciones)."""
    ident = identidad_de(request)
    return ident["upn"] or ident["nombre"] or "widget"


def usuario_para_api(request, maxlen=None):
    """
    Nombre del operador para APIs externas: parte local del UPN (antes del @),
    sin espacios, opcionalmente truncado a maxlen. "" si no hay sesión.
    """
    local = (identidad_de(request)["upn"] or "").split("@")[0]
    limpio = "".join(local.split())
    return limpio[:maxlen] if maxlen else limpio


def ip_de(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def registrar(request, *, action, target_type="", target_id="", endpoint="",
              payload_summary=None, response_status=None, success=True,
              error_detail="", dni=""):
    """Escribe una fila de AuditLog. Silenciosa ante cualquier error."""
    try:
        from .models import AuditLog
        ident = identidad_de(request)
        AuditLog.objects.create(
            user_upn=ident["upn"], user_oid=ident["oid"], user_name=ident["nombre"],
            action=action, target_type=target_type, target_id=str(target_id or ""),
            endpoint=endpoint or getattr(request, "path", ""),
            payload_summary=payload_summary or {},
            response_status=response_status, success=success,
            error_detail=(error_detail or "")[:2000],
            ip=ip_de(request), dni=str(dni or ""),
        )
    except Exception as e:  # nunca romper la request por auditoría
        logger.warning("No se pudo registrar AuditLog (%s): %s", action, e)

"""
Núcleo de autorización RBAC.

- La identidad del usuario (upn/oid/nombre/grupos) vive en request.session,
  puesta por el callback/exchange MSAL (views_auth.py).
- Los permisos (grupo -> recurso) viven en DB, cacheados e invalidados por signal.
- El hot path (usuario_puede) NO toca la DB: intersecta la lista de grupos de la
  sesión contra el mapa cacheado.
"""
from django.conf import settings
from django.core.cache import cache

_CACHE_KEY = "rbac_mapa_v1"
_CACHE_TTL = 300  # red de seguridad ante multi-worker; la invalidación por signal es la vía principal


# --------------------------------------------------------------------------- #
# Identidad
# --------------------------------------------------------------------------- #
def esta_autenticado(request) -> bool:
    return bool(request.session.get("upn"))


def identidad_de(request) -> dict:
    """Identidad del usuario logueado (tolerante a sesión anónima)."""
    return {
        "upn": request.session.get("upn"),
        "oid": request.session.get("oid"),
        "nombre": request.session.get("nombre"),
        "grupos": request.session.get("grupos") or [],
    }


def calcular_es_superadmin(upn: str, grupos) -> bool:
    """
    Raíz de confianza anti-lockout: se calcula contra el ENV, NO contra la DB
    (la DB de permisos solo la puede poblar un superadmin).
    """
    upn = (upn or "").lower()
    if upn and upn in getattr(settings, "WIDGET_SUPERADMINS", []):
        return True
    gids = getattr(settings, "WIDGET_SUPERADMIN_GROUP_IDS", [])
    if gids and set(gids) & {str(g).lower() for g in (grupos or [])}:
        return True
    return False


def es_superadmin(request) -> bool:
    return bool(request.session.get("es_superadmin"))


# --------------------------------------------------------------------------- #
# Mapa de permisos (cacheado)
# --------------------------------------------------------------------------- #
def _cargar_mapa():
    """recurso_key -> frozenset(oids en minúscula). Una sola query."""
    from .models import PermisoRecurso
    mapa = {}
    qs = (
        PermisoRecurso.objects
        .filter(grupo__activo=True)
        .values_list("recurso_key", "grupo__oid")
    )
    for rkey, oid in qs:
        mapa.setdefault(rkey, set()).add((oid or "").lower())
    return {k: frozenset(v) for k, v in mapa.items()}


def _mapa_permisos():
    mapa = cache.get(_CACHE_KEY)
    if mapa is None:
        mapa = _cargar_mapa()
        cache.set(_CACHE_KEY, mapa, _CACHE_TTL)
    return mapa


def invalidar_cache_rbac():
    cache.delete(_CACHE_KEY)
    cache.delete(_CACHE_KEY_ACCESO_TOTAL)


_CACHE_KEY_ACCESO_TOTAL = "rbac_acceso_total_v1"


def acceso_total_activo() -> bool:
    """Switch global: True = la matriz se ignora y todo autenticado accede a todo."""
    val = cache.get(_CACHE_KEY_ACCESO_TOTAL)
    if val is None:
        from .models import ConfiguracionRBAC
        val = ConfiguracionRBAC.obtener().acceso_total
        cache.set(_CACHE_KEY_ACCESO_TOTAL, val, _CACHE_TTL)
    return bool(val)


# --------------------------------------------------------------------------- #
# Chequeo de autorización
# --------------------------------------------------------------------------- #
def usuario_puede(request, recurso_key) -> bool:
    """Autorización pura. Asume que la autenticación ya se verificó."""
    if es_superadmin(request):
        return True
    if acceso_total_activo():
        return True  # switch global: la matriz no aplica
    grupos_usuario = request.session.get("grupos") or []
    if not grupos_usuario:
        return False  # deny-by-default
    concedidos = _mapa_permisos().get(recurso_key, frozenset())
    if not concedidos:
        return False
    usuario_oids = {str(g).lower() for g in grupos_usuario}
    return bool(concedidos & usuario_oids)


def grupo_que_concede(request, recurso_key) -> str:
    """
    Nombre legible (GrupoEntra.nombre) del primer grupo del operador que concede
    recurso_key. "" si ninguno (o el usuario no tiene grupos). No es hot-path:
    se usa solo al enviar la identidad a una API externa.
    """
    grupos_usuario = {str(g).lower() for g in (request.session.get("grupos") or [])}
    if not grupos_usuario:
        return ""
    from .models import GrupoEntra
    candidatos = (GrupoEntra.objects
                  .filter(activo=True, permisos__recurso_key=recurso_key)
                  .values_list("oid", "nombre"))
    for oid, nombre in candidatos:
        if (oid or "").lower() in grupos_usuario:
            return nombre or ""
    return ""

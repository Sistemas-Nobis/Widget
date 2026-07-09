from django.urls import path

from . import views_auth as va
from . import views_admin as adm

app_name = "cuentas"

urlpatterns = [
    # --- Autenticación (el navegador las ve con prefijo /widget/) ---
    path("auth/login_start", va.login_start, name="login_start"),
    path("auth/callback", va.callback, name="callback"),
    path("auth/exchange", va.exchange, name="exchange"),
    path("auth/status", va.auth_status, name="auth_status"),
    path("auth/handoff", va.handoff_poll, name="handoff"),
    path("auth/logout", va.logout, name="logout"),
    path("auth/dev_login", va.dev_login, name="dev_login"),  # solo DEBUG=True (pruebas locales)
    path("auth/whoami", va.whoami, name="whoami"),            # solo DEBUG=True (diagnóstico)

    # --- Superadmin (top-level, first-party) ---
    path("gestion/permisos/", adm.panel_permisos, name="panel_permisos"),
    path("gestion/permisos/estado/", adm.permisos_estado, name="permisos_estado"),
    path("gestion/permisos/guardar/", adm.permisos_guardar, name="permisos_guardar"),
    path("gestion/grupos/crear/", adm.grupo_crear, name="grupo_crear"),
    path("gestion/grupos/eliminar/", adm.grupo_eliminar, name="grupo_eliminar"),
    path("gestion/permisos/acceso-total/", adm.acceso_total_toggle, name="acceso_total_toggle"),
]

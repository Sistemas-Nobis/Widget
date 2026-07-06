from django.apps import AppConfig


class CuentasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cuentas'
    verbose_name = 'Cuentas y permisos'

    def ready(self):
        # Registra los signals que invalidan el cache de RBAC al editar permisos.
        from . import signals  # noqa: F401

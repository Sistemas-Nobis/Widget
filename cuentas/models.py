import uuid

from django.db import models


class AuthHandoff(models.Model):
    """
    Token de un solo uso que puentea la partición de cookies del popup de login
    (top-level widget.nobis.com.ar) hacia la partición del iframe embebido.

    El callback MSAL lo crea; el iframe lo canjea en /auth/exchange (POST) para
    materializar su cookie de sesión en su propia partición (CHIPS).
    """
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True, editable=False)
    channel_nonce = models.CharField(max_length=64, db_index=True)  # generado por el iframe (fallback opener-severed)
    upn = models.CharField(max_length=255)
    oid = models.CharField(max_length=64)
    nombre = models.CharField(max_length=255, blank=True)
    grupos = models.JSONField(default=list)          # oids de grupos Entra del claim
    es_superadmin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)  # now + 60s
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Handoff de autenticación"
        verbose_name_plural = "Handoffs de autenticación"

    def __str__(self):
        return f"handoff {self.token} ({self.upn})"


class GrupoEntra(models.Model):
    """Grupo de Azure AD / Entra ID habilitado para el RBAC del widget."""
    oid = models.CharField("Object ID (GUID)", max_length=64, unique=True, db_index=True)
    nombre = models.CharField(max_length=255, blank=True)   # displayName legible (informativo)
    activo = models.BooleanField(default=True)              # baja lógica sin borrar filas
    creado_en = models.DateTimeField(auto_now_add=True)
    creado_por = models.CharField(max_length=255, blank=True)  # UPN del superadmin

    class Meta:
        verbose_name = "Grupo Entra"
        verbose_name_plural = "Grupos Entra"
        ordering = ["nombre", "oid"]

    def __str__(self):
        return f"{self.nombre or '(sin nombre)'} [{self.oid}]"


class PermisoRecurso(models.Model):
    """
    Concesión (grant-only): la existencia de la fila = el grupo tiene acceso al recurso.
    Ausencia = denegado (deny-by-default).
    """
    grupo = models.ForeignKey(GrupoEntra, on_delete=models.CASCADE, related_name="permisos")
    recurso_key = models.CharField(max_length=64)   # una key de recursos.RECURSOS
    creado_en = models.DateTimeField(auto_now_add=True)
    creado_por = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Permiso"
        verbose_name_plural = "Permisos"
        unique_together = ("grupo", "recurso_key")
        indexes = [models.Index(fields=["recurso_key"])]

    def clean(self):
        from django.core.exceptions import ValidationError
        from .recursos import es_recurso_valido
        if not es_recurso_valido(self.recurso_key):
            raise ValidationError({"recurso_key": f"recurso_key inválido: {self.recurso_key}"})

    def __str__(self):
        return f"{self.grupo} -> {self.recurso_key}"

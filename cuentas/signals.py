"""Invalidación del cache de RBAC cuando el superadmin edita permisos/grupos."""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import GrupoEntra, PermisoRecurso, ConfiguracionRBAC
from .permisos import invalidar_cache_rbac


@receiver([post_save, post_delete], sender=PermisoRecurso)
@receiver([post_save, post_delete], sender=GrupoEntra)
@receiver([post_save, post_delete], sender=ConfiguracionRBAC)
def _invalidar_rbac(sender, **kwargs):
    invalidar_cache_rbac()

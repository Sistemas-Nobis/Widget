from django.contrib import admin

from .models import AuthHandoff, GrupoEntra, PermisoRecurso


@admin.register(GrupoEntra)
class GrupoEntraAdmin(admin.ModelAdmin):
    list_display = ("nombre", "oid", "activo", "creado_por", "creado_en")
    search_fields = ("nombre", "oid")
    list_filter = ("activo",)


@admin.register(PermisoRecurso)
class PermisoRecursoAdmin(admin.ModelAdmin):
    list_display = ("grupo", "recurso_key", "creado_por", "creado_en")
    search_fields = ("grupo__nombre", "grupo__oid", "recurso_key")
    list_filter = ("recurso_key",)


@admin.register(AuthHandoff)
class AuthHandoffAdmin(admin.ModelAdmin):
    list_display = ("token", "upn", "created_at", "expires_at", "consumed_at")
    search_fields = ("upn", "oid", "token")
    readonly_fields = ("token", "created_at")

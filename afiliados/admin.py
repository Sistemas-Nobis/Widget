from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user_upn", "grupo", "recurso", "action", "target_type",
                    "target_id", "success", "response_status", "ip")
    list_filter = ("action", "success", "recurso", "grupo")
    search_fields = ("user_upn", "user_oid", "grupo", "recurso", "target_id", "dni")
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

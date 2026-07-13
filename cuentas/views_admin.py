"""
Pantalla de superadmin: matriz grupos Entra × recursos.

Corre TOP-LEVEL en widget.nobis.com.ar/widget/gestion/... (no es iframe de 3ª parte),
así que usa CSRF de Django normal (no @csrf_exempt) y login por redirect.
"""
import csv
import json
import re

from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from .decoradores import superadmin_required_page, superadmin_required_json
from .models import GrupoEntra, PermisoRecurso, ConfiguracionRBAC
from .permisos import invalidar_cache_rbac, identidad_de
from .recursos import catalogo_serializable, RECURSO_KEYS

_GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


@superadmin_required_page
@require_GET
def panel_permisos(request):
    from django.conf import settings
    ident = identidad_de(request)
    return render(request, "cuentas/admin_rbac.html", {
        "usuario": ident.get("nombre") or ident.get("upn") or "superadmin",
        "grupos_sesion": ident.get("grupos") or [],
        "prefix": getattr(settings, "WIDGET_URL_PREFIX", ""),
    })


@superadmin_required_json
@require_GET
def permisos_estado(request):
    grupos = list(GrupoEntra.objects.filter(activo=True).values("id", "oid", "nombre"))
    asign = {}
    for recurso, gid in PermisoRecurso.objects.values_list("recurso_key", "grupo_id"):
        asign.setdefault(recurso, []).append(gid)
    return JsonResponse({
        "catalogo": catalogo_serializable(),
        "grupos": grupos,
        "asignaciones": asign,
        "acceso_total": ConfiguracionRBAC.obtener().acceso_total,
    })


@superadmin_required_json
@csrf_protect
@require_POST
def acceso_total_toggle(request):
    """Switch global: la matriz se ignora y todo usuario autenticado accede a todo."""
    from afiliados.audit import registrar
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse({"error": "body_invalido"}, status=400)

    activo = bool(payload.get("activo"))
    ident = identidad_de(request)
    conf = ConfiguracionRBAC.obtener()
    conf.acceso_total = activo
    conf.actualizado_por = ident.get("upn") or ""
    conf.save()
    invalidar_cache_rbac()
    registrar(request, action="admin_acceso_total", target_type="ConfiguracionRBAC",
              payload_summary={"acceso_total": activo}, success=True)
    return JsonResponse({"ok": True, "acceso_total": activo})


@superadmin_required_json
@csrf_protect
@require_POST
def permisos_guardar(request):
    from afiliados.audit import registrar
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse({"error": "body_invalido"}, status=400)

    asignaciones = payload.get("asignaciones")
    if not isinstance(asignaciones, dict):
        return JsonResponse({"error": "formato"}, status=400)
    for recurso in asignaciones:
        if recurso not in RECURSO_KEYS:
            return JsonResponse({"error": f"recurso_desconocido:{recurso}"}, status=400)

    ident = identidad_de(request)
    ids_validos = set(GrupoEntra.objects.values_list("id", flat=True))
    cambios = []
    with transaction.atomic():
        for recurso, ids in asignaciones.items():
            deseados = {int(i) for i in ids if int(i) in ids_validos}
            actuales = set(PermisoRecurso.objects.filter(recurso_key=recurso).values_list("grupo_id", flat=True))
            agregar, quitar = deseados - actuales, actuales - deseados
            for gid in agregar:
                PermisoRecurso.objects.create(recurso_key=recurso, grupo_id=gid,
                                              creado_por=ident.get("upn") or "")
            if quitar:
                PermisoRecurso.objects.filter(recurso_key=recurso, grupo_id__in=quitar).delete()
            if agregar or quitar:
                cambios.append({"recurso": recurso, "agregados": sorted(agregar), "quitados": sorted(quitar)})
    invalidar_cache_rbac()
    registrar(request, action="admin_permisos_guardar", target_type="PermisoRecurso",
              payload_summary={"cambios": cambios}, success=True)
    return JsonResponse({"ok": True, "cambios": cambios})


@superadmin_required_json
@csrf_protect
@require_POST
def grupo_crear(request):
    from afiliados.audit import registrar
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse({"error": "body_invalido"}, status=400)

    oid = (payload.get("oid") or "").strip()
    nombre = (payload.get("nombre") or "").strip()
    if not _GUID_RE.match(oid):
        return JsonResponse({"error": "oid_invalido"}, status=400)
    if not nombre:
        return JsonResponse({"error": "nombre_requerido"}, status=400)

    ident = identidad_de(request)
    grupo, creado = GrupoEntra.objects.get_or_create(
        oid=oid.lower(), defaults={"nombre": nombre, "creado_por": ident.get("upn") or ""})
    if not creado:
        grupo.nombre = nombre
        grupo.activo = True
        grupo.save(update_fields=["nombre", "activo"])
    invalidar_cache_rbac()
    registrar(request, action="admin_grupo_crear", target_type="GrupoEntra",
              target_id=str(grupo.id), payload_summary={"oid": oid, "nombre": nombre}, success=True)
    return JsonResponse({"ok": True, "id": grupo.id})


@superadmin_required_json
@csrf_protect
@require_POST
def grupo_eliminar(request):
    from afiliados.audit import registrar
    try:
        payload = json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return JsonResponse({"error": "body_invalido"}, status=400)

    gid = payload.get("id")
    grupo = GrupoEntra.objects.filter(id=gid).first()
    if not grupo:
        return JsonResponse({"error": "no_existe"}, status=404)
    removidos = list(grupo.permisos.values_list("recurso_key", flat=True))
    grupo.permisos.all().delete()
    grupo.activo = False
    grupo.save(update_fields=["activo"])
    invalidar_cache_rbac()
    registrar(request, action="admin_grupo_eliminar", target_type="GrupoEntra",
              target_id=str(grupo.id), payload_summary={"oid": grupo.oid, "permisos_removidos": removidos}, success=True)
    return JsonResponse({"ok": True})


# --------------------------------------------------------------------------- #
# Vista de auditoría
# --------------------------------------------------------------------------- #
def _filtrar_auditoria(request):
    """Queryset de AuditLog filtrado por los GET params. Reusado por datos y export."""
    from afiliados.models import AuditLog
    qs = AuditLog.objects.all()
    g = request.GET
    q = (g.get("q") or "").strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(user_upn__icontains=q) | Q(user_name__icontains=q) | Q(target_id__icontains=q))
    if g.get("action"):
        qs = qs.filter(action=g["action"])
    if g.get("grupo"):
        qs = qs.filter(grupo=g["grupo"])
    if g.get("recurso"):
        qs = qs.filter(recurso=g["recurso"])
    if g.get("success") in ("0", "1"):
        qs = qs.filter(success=(g["success"] == "1"))
    if g.get("desde"):
        qs = qs.filter(created_at__date__gte=g["desde"])
    if g.get("hasta"):
        qs = qs.filter(created_at__date__lte=g["hasta"])
    return qs.order_by("-created_at")


@superadmin_required_page
@require_GET
def panel_auditoria(request):
    from django.conf import settings
    from afiliados.models import AuditLog
    ident = identidad_de(request)
    grupos = list(
        GrupoEntra.objects.filter(activo=True).values_list("nombre", flat=True)
    )
    return render(request, "cuentas/auditoria.html", {
        "usuario": ident.get("nombre") or ident.get("upn") or "superadmin",
        "prefix": getattr(settings, "WIDGET_URL_PREFIX", ""),
        "acciones": AuditLog.ACTIONS,
        "grupos": grupos,
        "recursos": catalogo_serializable_pairs(),
    })


def catalogo_serializable_pairs():
    from .recursos import RECURSOS
    return [(k, v[0]) for k, v in RECURSOS.items()]


@superadmin_required_json
@require_GET
def auditoria_datos(request):
    from django.core.paginator import Paginator
    qs = _filtrar_auditoria(request)
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except ValueError:
        page = 1
    paginator = Paginator(qs, 50)
    pg = paginator.get_page(page)
    filas = [{
        "created_at": f.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "usuario": f.user_upn or f.user_name or "",
        "grupo": f.grupo,
        "recurso": f.recurso,
        "action": f.get_action_display(),
        "action_key": f.action,
        "target": (f"{f.target_type}:{f.target_id}" if f.target_id
                   else (f"DNI {f.dni}" if f.dni else f.target_type)),
        "success": f.success,
        "status": f.response_status,
        "ip": f.ip or "",
        "dni": f.dni,
    } for f in pg.object_list]
    return JsonResponse({
        "filas": filas,
        "page": pg.number,
        "num_pages": paginator.num_pages,
        "total": paginator.count,
    })


@superadmin_required_json
@require_GET
def auditoria_metricas(request):
    from django.utils import timezone
    from afiliados.models import AuditLog
    hoy = timezone.localdate()
    base_hoy = AuditLog.objects.filter(created_at__date=hoy)
    return JsonResponse({
        "total": AuditLog.objects.count(),
        "logins_hoy": base_hoy.filter(action="login").count(),
        "usuarios_hoy": base_hoy.exclude(user_upn="").values("user_upn").distinct().count(),
        "fallidos_hoy": base_hoy.filter(success=False).count(),
    })


@superadmin_required_page
@require_GET
def auditoria_export(request):
    qs = _filtrar_auditoria(request)[:50000]   # tope de seguridad
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="auditoria_widget.csv"'
    resp.write("﻿")  # BOM para Excel
    w = csv.writer(resp)
    w.writerow(["Fecha", "Usuario", "Nombre", "Grupo", "Recurso", "Accion",
                "Target tipo", "Target id", "Exito", "Status", "IP", "DNI"])
    for f in qs:
        w.writerow([f.created_at.strftime("%Y-%m-%d %H:%M:%S"), f.user_upn, f.user_name,
                    f.grupo, f.recurso, f.action, f.target_type, f.target_id,
                    "si" if f.success else "no", f.response_status or "", f.ip or "", f.dni])
    return resp

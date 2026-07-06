"""
Pantalla de superadmin: matriz grupos Entra × recursos.

Corre TOP-LEVEL en widget.nobis.com.ar/widget/gestion/... (no es iframe de 3ª parte),
así que usa CSRF de Django normal (no @csrf_exempt) y login por redirect.
"""
import json
import re

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from .decoradores import superadmin_required_page, superadmin_required_json
from .models import GrupoEntra, PermisoRecurso
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
    })


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

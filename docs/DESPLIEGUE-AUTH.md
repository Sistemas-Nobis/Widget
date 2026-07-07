# Despliegue: Login Azure AD + RBAC del Widget

Guía operativa para activar la autenticación (Entra ID / MSAL), la atribución por
usuario y el control de acceso por grupos. El código ya está en la rama
`feat/azure-ad-login-rbac`. Con `WIDGET_AUTH_ENABLED=False` (default) todo queda
**dormido** y el widget funciona como antes.

---

## 0. PASO BLOQUEANTE — spike del `<iframe>` del host (go / no-go)

El host que embebe el widget está en **otro dominio** y **no lo controlamos**. Todo el
login depende de atributos del tag `<iframe>` que pone ese host. **Antes de activar nada**,
verificar contra el portal real:

1. Inspeccionar el `<iframe>` en el DOM del portal. Si tiene `sandbox`, debe incluir:
   `allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-forms`
   (y `allow-storage-access-by-user-activation` si algún día se soporta Safari).
2. Dentro del iframe (consola del navegador sobre el widget), probar:
   - `window.open('about:blank')` → no debe devolver `null` (si es `null`: faltan popups).
   - `document.cookie` accesible / `window.origin` ≠ `"null"` (si es opaco: falta `allow-same-origin`).

Si el sandbox es restrictivo y el host no coopera, el login in-frame **no es viable** con
ese host tal cual: escalar con el dueño del portal. No activar el flag hasta resolverlo.

---

## 1. App Registration (Entra ID)

Sobre la App Registration existente (la que se reutiliza entre apps):

- **Authentication → Web → Redirect URIs**: agregar
  - `https://widget.nobis.com.ar/widget/auth/callback` (prod)
  - `http://localhost:8000/auth/callback` (dev)
- **Certificates & secrets**: generar/usar un client secret → va a `MSAL_CLIENT_SECRET`.
- **Token configuration → Add groups claim → Security groups**, emitido en el **ID token**.
  (Se eligió "todos los grupos de seguridad".)
- **Overage (>200 grupos)**: para que usuarios con muchos grupos no queden sin permisos,
  agregar permiso de **aplicación** `GroupMember.Read.All` (o `Directory.Read.All`) +
  **consentimiento de admin**. Lo usa el fallback Graph (`cuentas/msal_utils.py`).
- Confirmar **single-tenant** y que el ID token está habilitado.

## 2. Variables de entorno (`.env`)

Ver `.env.example`. Claves nuevas:

```
WIDGET_AUTH_ENABLED=True            # activar el gate (dejar False para deploy dormido)
WIDGET_CROSS_SITE=True              # prod (iframe cross-site). En dev local: False
DJANGO_DEBUG=False                  # prerequisito duro en prod
DJANGO_SECRET_KEY=<clave-nueva>     # sacar la hardcodeada de settings

MSAL_CLIENT_ID=...
MSAL_TENANT_ID=...
MSAL_CLIENT_SECRET=...
MSAL_REDIRECT_URI=https://widget.nobis.com.ar/widget/auth/callback

WIDGET_SUPERADMINS=lazaro.gonzalez@nobis.com.ar   # break-glass anti-lockout (UPNs)
WIDGET_SUPERADMIN_GROUP_ID=<guid1>,<guid2>  # opcional, uno o varios separados por coma
```

> `WIDGET_URL_PREFIX` se deriva solo del path del `MSAL_REDIRECT_URI` (`/widget` en prod, vacío en dev).

## 3. Apache

Aplicar `deploy/apache-widget.conf.example` en el vhost HTTPS: `X-Forwarded-Proto`, CSP
`frame-ancestors` con el origin real del portal (reemplaza `X-Frame-Options: DENY`), y el
`Header edit ... Partitioned` para CHIPS. Verificar que `X-Forwarded-Proto: https` llega a Django.

## 4. Dependencias y migraciones

```
venv/Scripts/python.exe -m pip install -r requirements.txt   # incluye msal
# Parar el servicio (runserver) antes de migrar (sqlite + autoreload):
venv/Scripts/python.exe dbtools.py migrate
```
`manage.py` está intervenido (siempre runserver); por eso los comandos de gestión van por
`dbtools.py` (usa `django.setup()`).

## 5. Primer uso (bootstrap del RBAC)

1. Deploy con `WIDGET_AUTH_ENABLED=True` y tu UPN en `WIDGET_SUPERADMINS`.
2. Abrir **top-level** `https://widget.nobis.com.ar/widget/gestion/permisos/` → login MSAL → volvés como superadmin.
3. **Panel 1**: agregar grupos de Entra (pegar Object ID + nombre). El Object ID sale de
   Entra admin center → Groups → (grupo) → Overview → Object Id. Debe ser un grupo **visible en el token**.
4. **Panel 2**: tildar qué grupos acceden a cada vista/acción → Guardar (efecto inmediato).
5. Los operadores ya entran según sus grupos. Sin grupo con permiso → overlay (vista) / 403 (acción).

## 6. Cómo funciona el login en el iframe (resumen)

Botón "Iniciar sesión" → popup top-level (`/widget/auth/login_start`) → MSAL → `/widget/auth/callback`
crea un **handoff de un solo uso** → el popup lo pasa por `postMessage` → el iframe hace
`POST /widget/auth/exchange` (materializa su cookie de sesión en su partición CHIPS) → recarga.
Las demás pestañas del **mismo portal** se desbloquean solas (BroadcastChannel + polling a `/widget/auth/status`).

## 7. Atribución por usuario (dónde SÍ y dónde NO)

| Acción | Sistema | ¿Usuario real en el sistema externo? |
|---|---|---|
| Crear expediente | Gecros (tercero) | **No** — solo texto en `observaciones`; Gecros registra el service account `fastapi` |
| Subir archivo | Gecros (tercero) | **No** — la API solo recibe id + binario |
| Enviar bonificación | Nobis (propia) | **Sí** — `usuario` en payload + observación |
| Crear remito | Nobis (propia) | **Sí** — `usuario` en payload + observación |
| Asignar generador | Nobis (propia) | **Sí** — auditado |

En **todos** los casos, `AuditLog` (tabla local, visible en el admin de Django) registra el
usuario real — es el registro confiable independiente del sistema externo. Para atribución
real de expedientes en Gecros hace falta que Gecros exponga un campo de operador (pendiente
de confirmar con ese equipo).

## 8. Rollout y rollback

- **Rollback instantáneo**: `WIDGET_AUTH_ENABLED=False` + restart → gate dormido.
- **Revocación de acceso**: la membresía de grupos se fija al login; quitar a alguien de un
  grupo surte efecto en su próximo login o al expirar la sesión (**~9 h**). No es inmediato.

## 9. Límites conocidos

- El auto-refresh de "todos los iframes" aplica dentro del **mismo portal top-level** (confirmado: siempre el mismo).
- Safari no está soportado (se descartó; usa CHIPS). Firefox: requiere versión con soporte `Partitioned`.
- `LocMemCache` es por proceso: hoy corre un solo runserver. Si se pasa a multi-worker, migrar
  `CACHES` a un backend compartido (los permisos podrían quedar stale hasta 5 min entre workers).

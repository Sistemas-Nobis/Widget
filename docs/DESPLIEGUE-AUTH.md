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

  **Prod corre con mod_wsgi** (`WSGIScriptAlias /widget` en
  `/etc/apache2/sites-available/widget-le-ssl.conf`; el `WSGIDaemonProcess` está en el
  vhost `:80`), no con runserver + ProxyPass. Aplicar `deploy/apache-widget.conf.example`
  en el vhost HTTPS. Puntos que costaron caro en el despliegue del 2026-07-09:

  - **`WSGIApplicationGroup %{GLOBAL}` es obligatorio**: sin eso MSAL/requests se
    deadlockea en el subintérprete y `login_start` cuelga (504) con el resto de la app sana.
  - **`WSGIDaemonProcess ... request-timeout=60 processes=2 threads=15`** (red de seguridad):
    el `WSGIDaemonProcess` real vive en `/etc/apache2/sites-available/widget.conf` (el vhost
    `:80`), **no** en el vhost SSL. Agregarle `request-timeout=60` para que mod_wsgi reinicie
    el daemon solo si un hilo queda colgado (así un futuro cuelgue del backend —como el del
    2026-07-13, en que appmobile dejó de responder y sin timeouts se clavaron los 15 hilos y
    el sitio dio 503 hasta reiniciar Apache— se autorrecupera). `processes=2` aísla el fallo.
    **Este cambio hay que aplicarlo A MANO en el `widget.conf` de prod**; el ejemplo de
    `deploy/apache-widget.conf.example` lo documenta pero no puede definir el daemon por él.
    Nota: con `processes=2` el `LocMemCache` deja de ser único por servidor (ver §9).
  - El `X-Frame-Options: DENY` de Django hay que quitarlo con `Header unset` **y**
    `Header always unset` (la respuesta de mod_wsgi va por la tabla onsuccess).
  - `Header edit* ... Partitioned` para `widget_sessionid` y `csrftoken` (CHIPS).
  - `RequestHeader set X-Forwarded-Proto "https"`.
  - Estáticos: alias específicos a `staticfiles/` para lo nuevo, y el Alias general
    en `home/static` para no congelar los JSON que la app reescribe en runtime
    (ver comentarios del `.example`).
  - Permisos (el daemon corre como `www-data`): `.env` legible (644) — si no,
    python-dotenv tumba el settings y TODO da 500 — y los JSON runtime de
    `home/static` escribibles (666); un `git stash pop` los recrea 664.

  ## 4. Dependencias, estáticos y migraciones (Linux / mod_wsgi)

  venv/bin/python -m pip install -r requirements.txt   # incluye msal
  venv/bin/python dbtools.py collectstatic --noinput   # llena staticfiles/

  Parar el widget antes de migrar (sqlite). Con mod_wsgi eso es sacar los vhosts

  (el otro sitio del servidor no se ve afectado):

  sudo a2dissite widget widget-le-ssl && sudo systemctl reload apache2
  venv/bin/python dbtools.py migrate
  venv/bin/python dbtools.py check
  sudo a2ensite widget widget-le-ssl && sudo systemctl reload apache2

  Para recargar código o `.env` **sin** parar el servicio (activación/rollback del flag):
  `touch /home/widget/config/wsgi.py` reinicia el daemon mod_wsgi, sin sudo.

  `manage.py` es el estándar de Django (restaurado el 2026-07-13; antes estaba intervenido
  para correr siempre `runserver`). Los comandos de gestión pueden ir por `manage.py migrate/
  check/...` o, equivalentemente, por `dbtools.py` (que usa `django.setup()` + `call_command`).

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
- `LocMemCache` es por proceso: prod corre con mod_wsgi y, con la config recomendada
  `processes=2` (ver §3), la caché deja de ser única por servidor —cada worker tiene la suya—,
  así que los permisos RBAC pueden quedar stale hasta ~5 min entre workers. Si eso molesta,
  migrar `CACHES` a un backend compartido (Redis/DB).

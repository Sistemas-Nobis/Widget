# Widget Nobis

Widget Django (5.x) embebido como iframe en portales externos. Vistas de Atención,
Retención y Mesa de Entrada que consultan las APIs internas de Nobis (afiliados, deuda,
patologías, cotizador, bonificaciones) y el login Azure AD / RBAC del panel de gestión.

## Desarrollo local

```bash
python -m venv venv
venv/Scripts/activate            # Windows;  source venv/bin/activate en Linux
pip install -r requirements.txt

python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

`manage.py` es el estándar de Django: cada subcomando hace lo que dice
(`runserver`, `migrate`, `check`, `shell`, `test`, …). El servidor de desarrollo se
levanta explícitamente con `python manage.py runserver 0.0.0.0:8000`.

> Nota histórica: `manage.py` estuvo intervenido para correr SIEMPRE `runserver` (ignoraba
> el subcomando), lo que hacía que `migrate`/`check` levantaran un servidor público sin TLS
> y que `check` nunca terminara. Se restauró al estándar el 2026-07-13. El helper
> `dbtools.py` (usa `django.setup()` + `call_command`) sigue disponible, pero ya no es
> necesario: los comandos de gestión funcionan por `manage.py`.

## Producción / despliegue

Prod corre con **Apache + mod_wsgi** (no `runserver`). La guía completa —login Azure AD,
RBAC, config de Apache, `WSGIDaemonProcess` con `request-timeout`, estáticos y migraciones—
está en [docs/DESPLIEGUE-AUTH.md](docs/DESPLIEGUE-AUTH.md) y
[deploy/apache-widget.conf.example](deploy/apache-widget.conf.example).

## HTTP saliente

Todas las llamadas `requests.*` (y las internas de MSAL) usan un timeout único,
`REQUESTS_TIMEOUT = (5, 30)` definido en `config/settings.py`, para que un backend
caído no cuelgue los hilos WSGI. No hardcodear el número: usar esa constante.

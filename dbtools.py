"""
Ejecutor de comandos de gestión de Django.

manage.py está intervenido para correr SIEMPRE runserver (ignora argv), así que
makemigrations/migrate/showmigrations no se pueden lanzar por la vía normal.
Este script inicializa Django con django.setup() y delega en call_command.

Uso:
    python dbtools.py makemigrations cuentas afiliados
    python dbtools.py migrate
    python dbtools.py showmigrations

Importante: parar el servicio (runserver) antes de migrar (sqlite + autoreload).
"""
import os
import sys

import django


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from django.core.management import call_command
    args = sys.argv[1:]
    if not args:
        print("Uso: python dbtools.py <comando> [args...]  (ej: makemigrations cuentas afiliados)")
        sys.exit(1)
    call_command(*args)


if __name__ == "__main__":
    main()

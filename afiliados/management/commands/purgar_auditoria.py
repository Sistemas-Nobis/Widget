"""
Purga manual de registros viejos de AuditLog (no se ejecuta solo).
Uso: python dbtools.py purgar_auditoria --dias 90
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from afiliados.models import AuditLog


class Command(BaseCommand):
    help = "Borra registros de AuditLog más viejos que N días (default 90)."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=90,
                            help="Antigüedad en días a partir de la cual se borra (default 90).")

    def handle(self, *args, **opts):
        dias = opts["dias"]
        limite = timezone.now() - timedelta(days=dias)
        n, _ = AuditLog.objects.filter(created_at__lt=limite).delete()
        self.stdout.write(self.style.SUCCESS(
            f"Borrados {n} registros de auditoría anteriores a {limite:%Y-%m-%d %H:%M}."
        ))

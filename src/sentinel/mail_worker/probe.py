"""Comprobación de la configuración SMTP durante el primer arranque.

El servidor no guarda credenciales SMTP en la base de datos: se leen de la
configuración de despliegue (``SENTINEL_SMTP_*``). El setup exige que estén
completas y que el servidor SMTP acepte la autenticación antes de crear el
primer superadministrador.
"""

from __future__ import annotations

import smtplib

from sentinel.bootstrap.settings import Settings
from sentinel.shared.errors import ValidationError


def check_smtp(settings: Settings) -> None:
    required = {
        "SENTINEL_SMTP_HOST": settings.smtp_host,
        "SENTINEL_SMTP_USER": settings.smtp_user,
        "SENTINEL_SMTP_PASSWORD": settings.smtp_password,
        "SENTINEL_SMTP_FROM": settings.smtp_from,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValidationError("Falta configurar SMTP: " + ", ".join(missing) + ".")
    try:
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
        ) as smtp:
            smtp.ehlo()
            if settings.smtp_starttls:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(settings.smtp_user, settings.smtp_password)
    except (OSError, smtplib.SMTPException) as exc:
        raise ValidationError("No se pudo validar la conexión SMTP.") from exc

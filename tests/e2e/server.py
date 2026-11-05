"""Backend para la suite E2E de la interfaz: sin SMTP real y con base propia.

La base se reinicia con `python -m tests.e2e.reset` antes de cada ejecución.
"""

from __future__ import annotations

import os

from sentinel.admin_api.app import create_app
from sentinel.bootstrap.container import Container
from sentinel.bootstrap.settings import Settings

E2E_ORIGIN = "http://localhost:3100"

settings = Settings(
    env="test",
    database_url=os.environ["SENTINEL_E2E_DSN"],
    require_https=False,
    cookie_secure=False,
    admin_origin=E2E_ORIGIN,
    public_base_url=E2E_ORIGIN,
    schema_dir=None,
    smtp_user="",
)

# En la suite no se abre conexión SMTP real; el setup usa una comprobación simulada.
app = create_app(Container(settings, smtp_check=lambda: None))

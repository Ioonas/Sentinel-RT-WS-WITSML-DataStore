"""Sentinel RT&WS WITSML DataStore.

Monolito modular con arquitectura de puertos y adaptadores. Los módulos de
núcleo (``witsml_application``, ``identity_access``, ``xml_schema``,
``audit_config``) no importan adaptadores (``wmls_transport``, ``admin_api``,
``persistence``, ``mail_worker``).
"""

__version__ = "1.0.3"
PRODUCT_NAME = "Sentinel RT&WS WITSML DataStore"
VENDOR = "Sentinel Real Time & Web Services"
API_VERSION = "1.4.1"
SCHEMA_VERSION = "1.4.1.1"

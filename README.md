# Sentinel RT&WS WITSML DataStore

Implementación de referencia del producto **Sentinel RT&WS WITSML DataStore 1.0.3**
sobre **WITSML 1.4.1.1**: Store API SOAP y API administrativa REST comparten
dominio, autorización, persistencia PostgreSQL y auditoría.

## Alcance de esta rebanada

- WMLS `GetVersion`, `GetCap`, `GetBaseMsg`, `GetFromStore`, `AddToStore`,
  `UpdateInStore` y `DeleteFromStore` sobre SOAP 1.1 con HTTP Basic.
- Objetos WITSML: `well`, `wellbore`, `log`, `trajectory` y `mudLog`,
  incluidos datos de curva, estaciones de trayectoria, intervalos de geología,
  parámetros de lodo, crecimiento y `changeLog` de solo lectura.
- API administrativa `/admin-api/v1`: primer arranque, sesión humana con cookie
  segura y CSRF, invitaciones, recuperación, usuarios, cuentas de servicio,
  credenciales de un solo uso, roles/acceso, inventario, borrado explícito,
  auditoría y salud.
- Arquitectura de puertos y adaptadores: el núcleo no importa FastAPI,
  SQLAlchemy ni SMTP.

Quedan fuera del MVP: conversión UOM, suscripciones push, ETP, paginación
propietaria y edición manual de XML.

## Requisitos

- Python 3.14
- PostgreSQL 18
- Node.js 24 (solo para la interfaz, opcional en esta rebanada)

## Puesta en marcha

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Crear rol y base de datos (una vez):

```sql
CREATE ROLE sentinel LOGIN PASSWORD 'sentinel_dev';
CREATE DATABASE sentinel OWNER sentinel;
```

Aplicar migraciones y arrancar:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\sentinel-api.exe
```

- API administrativa y OpenAPI: <http://localhost:8000/admin-api/v1/docs>
- Endpoint WMLS (WSDL en GET): <http://localhost:8000/witsml>
- Salud pública: <http://localhost:8000/health>

En desarrollo `.env.example` desactiva TLS y las cookies `Secure`; en
producción ambos deben permanecer activos y el endpoint WMLS debe publicarse
detrás de HTTPS.

### Primer arranque

`POST /admin-api/v1/setup` con correo/teléfono de contacto y el primer
superadministrador. Es idempotente en el sentido de que rechaza una segunda
ejecución y no existen credenciales predeterminadas.

### Worker de correo

```powershell
.\.venv\Scripts\sentinel-mail-worker.exe
```

La cola vive en PostgreSQL (`mail_outbox`); un fallo de SMTP no detiene las
APIs y se reintenta con retroceso exponencial.

### Interfaz administrativa

La UI Next.js (App Router, CSS Modules, tokens Industrial Slate v1.1) se sirve
aparte y consume la API mediante el rewrite `/admin-api/:path*`:

```powershell
cd frontend
npm install
npm run dev
```

- UI: <http://localhost:3000/admin/login>
- El backend debe estar en <http://localhost:8000> o definir
  `SENTINEL_API_URL` antes de arrancar Next.js.
- En producción: `npm run build` y `npm run start`; publicar UI y API bajo
  HTTPS para que la cookie `Secure` funcione.

Páginas disponibles: resumen, configuración del servidor, cuentas de servicio,
usuarios administrativos, roles y acceso, objetos WITSML, auditoría y perfil.
La UI nunca es una frontera de seguridad: todas las reglas se validan en el
backend.

## Estructura

```
src/sentinel/
  shared/              errores, reloj, IDs (núcleo)
  identity_access/     roles, permisos, sesiones, cuentas de servicio
  audit_config/        server_config, auditoría, cola de correo, salud
  xml_schema/          parseo seguro, XSD, serialización WITSML
  witsml_application/  casos de uso de las siete operaciones WMLS
  persistence/         adaptador PostgreSQL (SQLAlchemy async)
  wmls_transport/      adaptador de entrada SOAP 1.1
  admin_api/           adaptador de entrada REST + OpenAPI
  mail_worker/         worker SMTP
  bootstrap/           settings, composición y punto de entrada ASGI

frontend/
  app/admin/           rutas y páginas de administración
  components/          shell, primitivas UI y editores reutilizables
  lib/                 cliente tipado de la API, hooks y formato
  middleware.ts        redirección por presencia de sesión
```

Los ADR en `docs/adr/` documentan las decisiones de arquitectura, persistencia,
SOAP/XSD oficial, identidad y frontend.

## Contrato oficial y fase 0

`schemas/witsml/` contiene el WSDL oficial
`witsmlStoreAPI_v1.4.1.1.wsdl` y los XSD 1.4.1.1 de Energistics con sus
variantes `generated_{read,write,update,delete}_schemas`. El servicio publica el
WSDL sin cambios salvo `soap:address` y valida cada operación con la variante que
le corresponde; las respuestas de lectura se validan contra `xsd_schemas`.

Los namespaces oficiales son `/wsdl/120`, `/message/120` y
`/action/120/Store.<operación>`; `OptionsIn` se acepta URL-encoded y `GetBaseMsg`
usa `ReturnValueIn` (con `ErrorCodeIn` como compatibilidad). Los detalles y las
decisiones pendientes están en `docs/adr/0006-contrato-soap-xsd-oficial.md`.

Los MUST del Test Plan que la suite no ejecuta se cubren con pruebas propias y su
trazabilidad está en `docs/adr/0007-pruebas-propias-d15.md`. La suite oficial
`wPCTT1.1-t1.0-s1.0` se ejecutó completa sobre esta configuración con 0 fallos
(75 scripts aprobados, 0 omitidos, incluido `test22` con `cascadedDelete=true`);
la evidencia y los hashes están en `certification/README.md`. La certificación
Energistics no forma parte del desarrollo.

Regla de dependencias: `witsml_application`, `identity_access`,
`xml_schema`, `audit_config` y `shared` no importan `persistence`,
`wmls_transport`, `admin_api` ni `mail_worker`. Los adaptadores de entrada solo
usan puertos y servicios inyectados.

## Pruebas

```powershell
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\ruff.exe check .
```

Las pruebas de integración requieren PostgreSQL y se activan con
`SENTINEL_TEST_DSN`.

## Seguridad

- Sin secretos en logs ni auditoría; los detalles sensibles se redactan.
- Contraseñas con Argon2id; tokens de sesión, invitación y recuperación se
  almacenan como SHA-256 y son de un solo uso.
- Autorización en cada endpoint y en cada operación WMLS; denegación por
  defecto.
- Borrado en cascada solo con `cascadedDelete=true`; sin la opción, un padre con
  hijos devuelve `-432`. Cada objeto eliminado se registra en `changeLog`.
- XML sin DTD, entidades externas ni acceso a red (lxml endurecido).

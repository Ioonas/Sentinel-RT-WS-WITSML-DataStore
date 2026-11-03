# ADR 0002 — Persistencia PostgreSQL y transacciones por solicitud

- Estado: aceptado
- Fecha: 2026-10-31
- Contexto: spec §7 y §9

## Decisión

- PostgreSQL es la única fuente de verdad. Tablas separadas por tipo de objeto
  (`wells`, `wellbores`, `logs`, `trajectories`) con un mixin común
  (`identity_key` único, XML canónico, fechas y metadatos de filtro).
- Curvas, muestras de log y estaciones de trayectoria viven en tablas hijas con
  claves foráneas y borrado explícito; nunca hay `ON DELETE CASCADE`.
- `Container.request()` abre una `AsyncSession` por solicitud, construye los
  repositorios y confirma al salir sin excepción o revierte si falla.
- Alembic mantiene el esquema; `migrations/env.py` usa el DSN de `Settings`.
- La cola de correo (`mail_outbox`) también vive en PostgreSQL para que el
  worker sea independiente del proceso HTTP.

## Consecuencias

- Una operación WMLS con varios objetos es atómica.
- Sin `cascadedDelete=true`, el borrado de un padre con hijos devuelve `-432`
  (`NOT_BOTTOM_LEVEL`). Con la opción, la capa de aplicación elimina primero los
  dependientes y registra un `delete` en `changeLog` por cada objeto; las FK de
  PostgreSQL no eliminan filas.
- Los tests de integración usan una base separada (`sentinel_test`) y recrean
  el esquema con `Base.metadata`.

## Alternativas descartadas

- Cascada en base de datos: se descarta porque la cascada WITSML debe comprobar
  permisos y registrar `changeLog` explícito; `ON DELETE CASCADE` no puede
  hacerlo sin perder trazabilidad.
- Almacenar XML como único dato: impide filtrar por pozo, nombre o rango de
  índices sin cargar todos los documentos.

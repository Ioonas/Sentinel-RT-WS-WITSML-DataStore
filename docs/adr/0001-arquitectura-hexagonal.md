# ADR 0001 — Arquitectura de puertos y adaptadores

- Estado: aceptado
- Fecha: 2026-10-31
- Contexto: spec §6 y §2 (KISS, DRY, YAGNI)

## Decisión

El producto es un monolito modular con dependencias dirigidas hacia el núcleo:

```
wmls_transport ─┐
admin_api ──────┼──> witsml_application / identity_access / audit_config / xml_schema
mail_worker ────┘                 │
                                  └──> shared
persistence ─────────────────────────> puertos del núcleo (implementación)
bootstrap ───────────────────────────> todos (composición)
```

- `witsml_application`, `identity_access`, `audit_config`, `xml_schema` y
  `shared` son núcleo y no importan FastAPI, Starlette, SQLAlchemy, asyncpg,
  uvicorn, smtplib ni módulos adaptadores.
- `wmls_transport` y `admin_api` solo usan puertos y servicios inyectados.
  Ambos traducen el mismo caso de uso a SOAP o REST; no duplican reglas.
- `persistence` implementa los protocolos del núcleo con SQLAlchemy async.
- `bootstrap` es el único lugar que conoce a la vez núcleo y adaptadores.

## Consecuencias

- `tests/test_architecture.py` verifica la regla con análisis AST.
- Un cambio de protocolo (SOAP/REST) no toca reglas de negocio.
- La composición explícita evita un contenedor de DI pesado (KISS/YAGNI).

## Alternativas descartadas

- Microservicios por módulo: sobredimensionado para el alcance y el equipo.
- FastAPI/SQLAlchemy dentro del núcleo: acopla los casos de uso y dificulta las
  pruebas de contrato.

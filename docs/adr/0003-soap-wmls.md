# ADR 0003 — Transporte SOAP WMLS y XML endurecido

- Estado: aceptado
- Fecha: 2026-10-31
- Contexto: spec §6, §10 y fase 0

## Decisión

- Endpoint único `POST /witsml` con SOAP 1.1, HTTP Basic sobre TLS y XML en
  texto. `GET /witsml` publica el WSDL.
- Siete operaciones: `GetVersion`, `GetCap`, `GetBaseMsg`, `GetFromStore`,
  `AddToStore`, `UpdateInStore`, `DeleteFromStore`.
- Los errores WMLS viajan en `Result`/`SuppMsgOut`, no en el código HTTP.
- El parseo usa lxml con `resolve_entities=False`, `no_network=True`,
  `load_dtd=False` y rechazo explícito de `DOCTYPE`/`ENTITY`. El tamaño máximo
  de documento es 32 MiB.
- Si el XSD oficial no está presente en `schemas/witsml/1.4.1.1`, se usa
  `PermissiveSchemaValidator` y queda registrado como pendiente de fase 0. Si
  el WSDL oficial no está, se genera uno mínimo equivalente. El estado del
  contrato oficial se documenta en el ADR 0006.
- `GetCap` construye `capServer` desde `server_config` (DRY).

## Consecuencias

- La fase 0 debe copiar los XSD/WSDL oficiales y ejecutar el Test Plan; el
  código no cambia salvo el `soap:address`. Los artefactos oficiales ya están
  incorporados en `schemas/witsml/` (ADR 0006).
- Un `OptionsIn` sin `dataVersion` se acepta de forma tolerante; debe validarse
  contra el Test Plan oficial antes de certificar.

## Alternativas descartadas

- WS-Security/MTOM: el perfil acordado es Basic Auth + XML en texto.
- Parseo con `xml.etree` sin endurecer: riesgo de XXE y entidades.

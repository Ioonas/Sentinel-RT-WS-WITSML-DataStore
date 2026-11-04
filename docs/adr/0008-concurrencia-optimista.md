# ADR 0008 — Concurrencia optimista con `dTimLastChange`

- Estado: aceptado
- Fecha: 2026-11-04
- Contexto: spec §7 (contrato funcional WMLS), criterio de aceptación 18 y
  tabla de pruebas de concurrencia de §11

## Problema

El criterio 18 exige que una escritura concurrente incompatible no sobrescriba
silenciosamente el trabajo de otra. La API WITSML 1.4.1 no define un código de
conflicto ni un mecanismo de versión explícito; el único dato normativo de
cambio por objeto es `commonData/dTimLastChange`, que el servidor actualiza en
cada escritura y devuelve en las lecturas.

Sin una precondición, dos `UpdateInStore` simultáneos leen el mismo estado,
calculan su fusión y el último en confirmar pisa al primero. La suite oficial no
ejecuta ninguna prueba de concurrencia y ninguno de sus scripts envía
`dTimLastChange` en `UpdateInStore` ni en `DeleteFromStore` (verificado sobre los
15 scripts de actualización y los 15 de borrado), por lo que la solución debe
ser opcional para no romper la certificación.

## Decisión

- `UpdateInStore` y `DeleteFromStore` aceptan como **precondición opcional** el
  `commonData/dTimLastChange` del XML de entrada.
- El token se compara con el `changed_at` almacenado, en UTC y con precisión de
  microsegundos. Si no coincide:
  - actualización: `-1003` (`ERROR_UPDATING`);
  - borrado: `-1004` (`ERROR_DELETING`).
- El rechazo no persiste nada de ese elemento ni registra una entrada en
  `changeLog`. La transacción completa se revierte, de modo que una actualización
  múltiple tampoco deja cambios parciales.
- La fila se carga con `SELECT … FOR UPDATE` dentro de la misma transacción que
  aplica la escritura. El bloqueo serializa a los escritores y cierra la ventana
  entre la comprobación del token y el `UPDATE`/`DELETE`.
- El nuevo `dTimLastChange` se calcula **después** de adquirir el bloqueo para
  que el valor no retroceda respecto del escrito por la transacción anterior.
- Si el cliente no envía el token, se conserva el comportamiento clásico
  («último escritor gana»), que es el que esperan los clientes WITSML 1.4.1 y la
  suite oficial.
- `AddToStore` y `GetFromStore` no cambian. La precondición solo aplica a
  escrituras sobre objetos existentes.

## Implementación

| Pieza | Ubicación |
| --- | --- |
| Lectura del token del XML entrante | `xml_schema/documents.py::last_change_token` |
| Puertos con `for_update` | `witsml_application/ports.py` (cinco repositorios) |
| Bloqueo de fila | `persistence/repositories.py` (`with_for_update()`) |
| Comparación y error WMLS | `witsml_application/service.py::_require_matching_token` |
| Integración en casos de uso | `WitsmlStoreService._update` y `._delete` |

El token se lee del elemento recibido antes de `strip_server_fields`, porque ese
paso elimina precisamente los campos gestionados por el servidor del XML
fusionado.

## Pruebas

- `tests/test_wmls_musts.py::test_acceptance_18_last_change_token_guards_updates`
  cubre token obsoleto (`-1003` sin persistir ni dejar `changeLog`), token
  vigente, renovación de `dTimLastChange` y ausencia de token.
- `tests/test_wmls_musts.py::test_acceptance_18_concurrent_updates_have_single_winner`
  lanza dos actualizaciones concurrentes con el mismo token y exige exactamente
  un éxito y un `-1003`, con una sola entrada `update` en el `changeLog`.
- `tests/test_wmls_musts.py::test_acceptance_18_batch_conflict_persists_nothing`
  envía un lote con el primer elemento válido y el segundo con token obsoleto, y
  comprueba que ninguno de los dos se persiste.
- `test61` y `test94a` de la suite oficial se reejecutaron tras el cambio para
  confirmar que las lecturas y comparaciones de `dTimLastChange` siguen
  conformes.

## Consecuencias

- El bloqueo dura hasta el `commit` de la transacción de la solicitud. Las
  transacciones WMLS son cortas (un objeto o un lote pequeño), por lo que la
  contención es acotada; un cliente que abuse de lotes grandes puede retener el
  bloqueo y recibir `-1005` si se agota el tiempo de transacción.
- Un cliente que reciba `-1003`/`-1004` debe volver a leer el objeto, reconciliar
  su cambio y reintentar con el token nuevo.
- No se añade una columna de versión ni un `ETag` HTTP: `dTimLastChange` ya es
  parte del contrato WITSML y es visible para el cliente.
- El conflicto se comunica en `Result` con HTTP 200, como el resto de errores
  WMLS; no se usa `409`.

## Alternativas descartadas

- **Sin bloqueo, solo comparar el token**: deja abierta la carrera entre la
  lectura y la escritura; dos transacciones pueden leer el mismo `changed_at`
  antes de que ninguna confirme.
- **Aislamiento `SERIALIZABLE` para todas las escrituras**: resuelve el
  problema, pero introduce fallos de serialización en operaciones que no los
  necesitan y obliga a reintentos en el cliente.
- **Columna `version` incremental o `ETag`/`If-Match`**: no forma parte del
  contrato WITSML 1.4.1 y obligaría a los clientes a usar una extensión
  propietaria.
- **Rechazar siempre el token**: rompe a los clientes que envían el objeto
  completo leído previamente con un `dTimLastChange` válido pero destinado a
  otros fines.

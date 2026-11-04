# ADR 0007 — Pruebas propias de los MUST no ejecutados (D-15)

- Estado: aceptado
- Fecha: 2026-11-01
- Contexto: spec §10 (criterios 12, 13, 19, 29 y 36) y §11 «Pruebas propias
  de MUST no ejecutados» (D-15)

## Decisión

Los MUST del Test Plan oficial que la suite `wPCTT1.1-t1.0-s1.0` no ejecuta
—porque están marcados como *Deferred*, *In Progress* o porque el dataset
estándar no los provoca— se cubren con pruebas automatizadas propias en
`tests/test_wmls_musts.py` y `tests/test_wmls_soap.py`. Cada prueba cita el
identificador del Test Plan o el criterio de aceptación que cubre.

| Test Plan / criterio | Prueba automatizada | Qué verifica |
| --- | --- | --- |
| 12 | `test_d15_12_13_change_log_keeps_update_and_delete_entries` | Entrada `update` en `changeLog`, consultable con el filtro `dTimChange` de SQ-018. |
| 13 | `test_d15_12_13_change_log_keeps_update_and_delete_entries` | Entrada `delete` sobrevive al borrado del objeto y conserva `nameObject`. |
| 74 | `test_d15_74_get_from_store_truncates_by_max_data_nodes` | Truncamiento por `maxDataNodes` con código `+2` y sin nodos duplicados. |
| 75 | `test_d15_75_get_from_store_truncates_by_max_data_points` | Truncamiento por `maxDataPoints` con código `+2` y frontera estable. |
| 76c | `test_d15_76c_request_latest_values_for_decreasing_log` | `requestLatestValues` en log descendente y rechazo por encima de `maxRequestLatestValues` (`-1054`). |
| 82 | `test_d15_82_log_append_and_intersection_clearing_behavior` | *Clearing behavior* de la API §6.7.4.6: append conserva, intersección limpia y curva omitida intacta. |
| 83 | `test_wmls_gzip_responses` (en `tests/test_wmls_soap.py`) | Respuesta gzip con `Accept-Encoding: gzip`, `Vary` correcto e identidad cuando se rechaza. |
| 84 | `test_d15_84_client_compression_is_not_advertised` | Sin `compressionMethod` en `GetCap`; solicitud comprimida rechazada con fault 400. |
| 19 | `test_wmls_gzip_responses` + pruebas de `GetCap` | Negociación de compresión de respuesta conforme al criterio 19. |
| 6 y 7 | Pruebas existentes de `GetCap` e `id-only` | Capacidades publicadas y consultas de solo identificación. |
| 22 | `test_wmls_cascaded_delete_removes_descendants` | `cascadedDelete=true` elimina `well -> wellbore -> log/trajectory/mudLog` y registra `delete` por objeto. |
| -432 | `test_wmls_discovery_and_crud` + `test_wmls_cascaded_delete_removes_descendants` | Sin `cascadedDelete=true`, el padre con hijos se rechaza con `-432`. |
| `-427` y `-428` | `test_wmls_request_object_selection_option_rules` | `requestObjectSelectionCapability` con valor distinto de `none` exige ser el único keyword (`-427`) y una Minimum Query Template (`-428`); `none` restaura el comportamiento normal. |
| `-443` y `-453` | `test_wmls_uom_dictionary_validation` + `test_uom_dictionary_validation_follows_measure_types` | Toda medida declara `uom` (`-453`) y su valor pertenece a los `annotation` del diccionario oficial (`-443`), resolviendo el tipo XSD de cada elemento. |
| Criterio 12 | `test_d15_82_*` | Actualización parcial preserva curvas omitidas y distingue append de modificación interior. |
| Criterio 13 | `test_acceptance_13_index_type_and_duplicate_nodes` | Tipo de índice preservado y nodos con el mismo índice rechazados con `-463` sin sobrescribir. |
| Criterio 18 | `test_acceptance_18_*` (tres pruebas) | `dTimLastChange` como precondición opcional: token obsoleto devuelve `-1003` sin persistir ni registrar `changeLog`; dos escrituras concurrentes con el mismo token tienen un único ganador; un lote con conflicto no persiste cambios parciales. |
| Criterio 29 | `test_acceptance_29_soap_and_rest_share_use_cases` (×4 objetos) | El objeto creado por SOAP se lee por REST y el borrado por REST se refleja en SOAP. |
| Criterio 36 | Pruebas 74 y 75 | Los límites se provocan por separado (nodos y puntos). |

### Retención de 24 horas (pruebas 12 y 13)

El Test Plan pide esperar 23 h 59 min y volver a consultar la entrada. La
decisión **D-10** fija la retención del `changeLog` en **5 años sin purga**, por
lo que la espera no aporta información: si la entrada existe al cabo de segundos
y no hay proceso de purga, sigue existiendo al cabo de 24 horas. La prueba
verifica que la entrada permanece consultable con el mismo filtro SQ-018 que usa
el Test Plan y documenta la limitación de la espera.

### Clearing por canal (prueba 82)

La API 1.4.1 §6.7.4.6 exige limpiar por canal el rango implícito de la
actualización, no el `startIndex`/`endIndex` del encabezado. El Store no lo
hacía y se corrigió en `WitsmlApplicationService._clear_updated_channels`:

- Se calcula, por curva informada, el menor y el mayor índice donde la
  actualización trae valor.
- Se borran los valores previos de esa curva dentro de ese rango antes de
  insertar las filas nuevas.
- Una curva ausente de `mnemonicList` no se toca (criterio 12).
- Un append conserva los valores fuera de su rango implícito; una modificación
  interior deja en nulo el índice no informado.
- Se sigue registrando una entrada `update` en el `changeLog`, como espera el
  revisor del Test Plan 82 aunque la prueba figure como *Rejected*.

### Plantilla de selección (prueba 15)

La API 1.4.1 §6.6.2.1 exige que, cuando
`requestObjectSelectionCapability` vale algo distinto de `none`, sea el único
keyword de `OptionsIn` (`-427`) y que `QueryIn` sea la Minimum Query Template
(`-428`), por ejemplo `<wells><well/></wells>`. El servicio valida ambas reglas
antes de parsear la consulta y devuelve una plantilla con los elementos de
selección (`uid`, `name`, `numGovt`, `numAPI`, `dTimLastChange`). El valor
`none` mantiene el comportamiento normal y permite el resto de keywords.

### Diccionario de unidades (§6.4.4.2 y §6.7.4.3)

La API exige que todo dato de medida declare `uom` (`-453`) y que el valor
coincida con un atributo `annotation` de `witsmlUnitDict.xml` (`-443`). El XSD
oficial ya marca `uom` como obligatorio, pero su enumeración es por clase de
cantidad y el error saldría como XML no conforme. `UomValidator` aplica las
reglas antes del XSD:

- El diccionario oficial se vendoriza en
  `schemas/witsml/1.4.1.1/witsml_v1.4.1.1_data/ancillary/witsmlUnitDict.xml`
  (700 052 bytes, SHA-256 `4475747828d983b8cfc5a7a7cf4e47a219bdd2cf49cc8a204cd1ba487f08bbaa`)
  y se carga de forma perezosa una sola vez.
- El índice de tipos se construye desde los XSD de la variante de escritura y
  sigue la declaración de cada elemento; así un mismo nombre de elemento solo se
  trata como medida cuando su tipo XSD lo es. Las ramas no resolubles
  (`customData` usa `xsd:any`) validan el `uom` presente pero no exigen uno.
- Un `uom` vacío o ausente en una medida devuelve `-453`; un valor fuera del
  diccionario devuelve `-443`. La validación se ejecuta en `AddToStore` y
  `UpdateInStore`, antes del XSD.

### Transporte SOAP

Una solicitud con cuerpo ilegible —incluida una solicitud comprimida, que D-01
no soporta— se responde con un *fault* SOAP 400. Antes devolvía un JSON 422 de
FastAPI, lo que rompía el contrato del endpoint. `parse_soap_request` envuelve
el `ValidationError` del parser en `SoapEnvelopeError`.

## Consecuencias

- La evidencia de D-15 es reproducible con `pytest tests/test_wmls_musts.py` y
  no depende de la herramienta oficial.
- La suite oficial sigue siendo la fuente de verdad para las pruebas que sí
  ejecuta; estas pruebas no la sustituyen.
- Cambiar la semántica de actualización de logs o de compresión exige actualizar
  este ADR y las pruebas citadas.

## Alternativas descartadas

- Esperar 24 horas reales en la suite: coste alto y sin valor probatorio con una
  retención de 5 años sin purga.
- Marcar las pruebas 12/13 como no cubiertas: incumple D-15.
- Dejar el clearing fuera del alcance: incumple la API 1.4.1 §6.7.4.6 y el
  criterio 12.

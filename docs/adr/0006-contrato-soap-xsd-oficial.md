# ADR 0006 — Contrato SOAP/XSD oficial de WITSML 1.4.1.1

- Estado: aceptado
- Fecha: 2026-10-31
- Contexto: spec §1, §5, §10 y cierre de fase 0

## Decisión

- Los artefactos oficiales de Energistics viven en `schemas/witsml/`:
  `witsmlStoreAPI_v1.4.1.1.wsdl` y el árbol
  `1.4.1.1/witsml_v1.4.1.1_data/` con `xsd_schemas`,
  `generated_{read,write,update,delete}_schemas`, `abstract_v1.0`,
  `aggregate_1.0` y los esquemas GML referenciados. No se modifican.
- `GET /witsml` publica el WSDL oficial cambiando **solo**
  `soap:address/@location` por la URL base configurada. Si el archivo no está
  instalado se genera un contrato RPC/encoded equivalente para desarrollo; la
  certificación exige el oficial.
- El WSDL oficial es RPC/encoded con `targetNamespace` `/wsdl/120`, mensajes en
  `/message/120` y acciones `SOAPAction: /action/120/Store.<operación>`. El
  adaptador responde en `/message/120` y acepta además el formato histórico
  `<ns>/<operación>`.
- `GetVersion` anuncia únicamente el esquema `1.4.1.1`. `GetCap` declara la API
  1.4.1 y el esquema 1.4.1.1.
- `GetBaseMsg` usa la parte oficial `ReturnValueIn`; se conserva
  `ErrorCodeIn` como compatibilidad de entrada.
- `OptionsIn` se interpreta como
  `application/x-www-form-urlencoded` (`dataVersion=1.4.1.1&returnElements=...`)
  y, por compatibilidad, como XML legado. Un `dataVersion` presente distinto de
  `1.4.1.1` devuelve `-423`; su ausencia se tolera.
- `returnElements=requested` es el valor por defecto del API: la respuesta de
  `GetFromStore` contiene solo los elementos y atributos escritos en la
  plantilla de consulta, más `name`/`nameWell`/`nameWellbore` para conservar la
  identidad y validar contra el XSD normativo de lectura. `all` trata la
  plantilla como si pidiera todos los elementos; los modos restantes
  (`id-only`, `header-only`, `data-only`, `station-location-only`) mantienen su
  conjunto propio y añaden la selección explícita.
- La validación usa la variante XSD de cada operación: `generated_write` en
  alta, `generated_update` en actualización y `xsd_schemas` en lectura. Las
  respuestas de `GetFromStore` se validan contra el esquema de lectura en las
  pruebas de integración.
- Se aplican fielmente las restricciones del esquema oficial: `version` en la
  raíz, plural `trajectorys` (se aceptan `trajectories` en consultas), curva de
  índice identificada por `mnemonic == indexCurve`, `typeLogData` obligatorio,
  `typeTrajStation`/`md` en estaciones y UOM de ángulos `dega`.
- `dTimCreation` y `dTimLastChange` son hijos de `commonData`;
  `objectGrowing` encabeza `grp_log`/`grp_trajectory`. `changeLog` se serializa
  con `uidObject`, `nameWell`/`nameWellbore`/`nameObject`, `objectType`,
  `lastChangeType` y `changeHistory`, sin atributos no previstos por el XSD. Los
  nombres contextuales se persisten para sobrevivir al borrado del objeto.
- `DeleteFromStore` acepta `cascadedDelete=true` (capacidad publicada por
  `GetCap`): el servidor comprueba permisos sobre todos los dependientes y los
  elimina en orden `well -> wellbore -> log/trajectory/mudLog`, registrando una
  entrada `delete` por objeto. Sin la opción, un padre con hijos sigue
  devolviendo `-432` (`NOT_BOTTOM_LEVEL`). La cascada se resuelve en la capa de
  aplicación, no con `ON DELETE CASCADE` de PostgreSQL.

## Consecuencias

- Cambiar de versión de WITSML exige reemplazar el árbol `schemas/witsml/` y
  revisar los ADR; no se parchean los XSD.
- La suite oficial `wPCTT1.1-t1.0-s1.0` se ejecuta contra este contrato; la
  evidencia y los hashes se archivan en `certification/README.md`.
- Queda pendiente decidir, con el Test Plan, si `GetCap` sin `dataVersion` debe
  devolver `-423`; hasta entonces se mantiene la tolerancia documentada.
- La certificación Energistics y los trámites comerciales quedan fuera del
  alcance de desarrollo.

## Alternativas descartadas

- Publicar un WSDL propio: impediría la validación de interoperabilidad contra
  el contrato oficial.
- Validar todo con un único XSD: no expresa las restricciones de alta,
  actualización y borrado.
- Serializar `changeLog` con atributos propietarios: incumple
  `obj_changeLog.xsd` y rompe el `GetFromStore` certificable.

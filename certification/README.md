# Certificación WITSML 1.4.1.1 — ejecución de wPCTT

Este directorio contiene utilidades para ejecutar la suite oficial
`wPCTT1.1-t1.0-s1.0` contra un Store Sentinel. **No** forma parte del runtime
del producto y **no** modifica los scripts de prueba ni los esquemas oficiales.

## Requisitos

- Windows con la herramienta oficial descomprimida, por ejemplo
  `D:\Descargas-J\Docs\wPCTT1.1-t1.0-s1.0`.
- Backend Sentinel accesible desde la herramienta. Para un ensayo local:
  `http://localhost:8000/witsml` con `SENTINEL_REQUIRE_HTTPS=false`.
- Base de datos dedicada al ensayo. `load_data_set.exe` **escribe** el dataset
  estándar (pozos `Energistics-*`), así que no debe apuntarse a producción.
- Una cuenta de servicio WMLS con permisos `read`/`write`/`delete` sobre `*`.

## 1. Preparar la cuenta de servicio

Con una sesión de superadministrador:

```powershell
$login = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/admin-api/v1/auth/sessions" `
  -ContentType "application/json" `
  -Body '{"email":"<admin>","password":"<clave>"}' `
  -SessionVariable session

$account = Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/admin-api/v1/service-accounts" `
  -ContentType "application/json" `
  -Headers @{ "X-CSRF-Token" = $session.Cookies["sentinel_csrf"].Value } `
  -WebSession $session `
  -Body (@{
      name = "wcat.certification"
      role = "writer"
      grants = @(
        @{ object_type = "*"; action = "read" },
        @{ object_type = "*"; action = "write" },
        @{ object_type = "*"; action = "delete" }
      )
    } | ConvertTo-Json -Depth 5)

$secret = $account.credential.secret   # se muestra una sola vez
```

No guardar `$secret` en el repositorio ni en los logs.

## 2. Configurar la herramienta

```powershell
python certification/prepare_wcat.py `
  --tool-home "D:\Descargas-J\Docs\wPCTT1.1-t1.0-s1.0" `
  --server-url "http://localhost:8000/witsml" `
  --username "wcat.certification" `
  --password "$secret"
```

El script crea `server/backup-<fecha>/` antes de escribir. Para revisar la
configuración sin modificarla:

```powershell
python certification/prepare_wcat.py --tool-home "..." `
  --server-url "http://localhost:8000/witsml" `
  --username "wcat.certification" --password x --check
```

## 3. Cargar el dataset estándar

Desde el directorio de la herramienta:

```powershell
cd "D:\Descargas-J\Docs\wPCTT1.1-t1.0-s1.0"
.\load_data_set.exe -as
```

Debe terminar sin errores y dejar los objetos `Energistics-well-0001`,
`Energistics-well-0002`, `Energistics-well-0003` y sus hijos. Comprobar con
`GetFromStore` o con el inventario administrativo antes de continuar.

## 4. Ejecutar la suite

### 4.1 Modo headless (recomendado)

`run_wpctt.py` arranca el mismo motor `wtl` que usa `wcat.exe`, sin GUI. Debe
ejecutarse con el Python 2.7.18 de la herramienta:

```powershell
& "$env:TEMP\py27msi\python.exe" certification\run_wpctt.py `
  "D:\Descargas-J\Docs\wPCTT1.1-t1.0-s1.0" testsuite
```

El código de salida es `0` solo si `witsml_result.txt` informa `Fail 0`. Los
contadores `wPCTT <script>: pass/fail/skip` que imprime el runner son
acumulados; la referencia fiable es la línea `!SCRIPT '<script>' completed` y la
ausencia de `!*** FAILURE`.

Antes de la suite hay que purgar el Store, cargar el dataset con
`load_data_set` (Paso 3) y dejar corriendo un publicador de datos creciente
(`data_grower_script`) mientras dure la ejecución. Sin él, las pruebas de
`objectGrowing` sobre `Energistics-w1-wb1-log-0001` y
`Energistics-w1-wb1-trajectory-0001` fallan por falta de filas nuevas.

### 4.2 Modo GUI

```powershell
.\wcat.exe
```

En la ventana:

1. Seleccionar el perfil `sentinel-certification` y pulsar **Connect**.
2. Confirmar que la versión de esquema detectada es `1.4.1.1`.
3. Pulsar **Connect** de nuevo solo si la sesión se perdió; el botón de carga
   de datos ya se ejecutó en el paso 3.
4. Ejecutar las pruebas de certificación (todas o por grupos) y esperar a que
   terminen.
5. Guardar el resultado indicado en **Test Suite Result Filename**.

Los logs quedan en `results/log_*.txt` y `results/log_*_soap.txt`.

## 5. Recoger evidencia

Copiar `results/log_<fecha>.txt`, su `_soap.txt` y `witsml_result.txt` a
`certification/results/` (ignorado por Git) y registrar los hashes en
`certification/manifests/` (también ignorado):

```powershell
$src   = "D:\Descargas-J\Docs\wPCTT1.1-t1.0-s1.0\results"
$dest  = "certification/results"
$stamp = Get-Date -Format "yyyyMMdd"
New-Item -ItemType Directory -Force -Path $dest, "certification/manifests" | Out-Null
Copy-Item "$src\log_2026*.txt" -Exclude "*_soap.txt" $dest -Force
Copy-Item "$src\log_2026*_soap.txt" $dest -Force
Copy-Item "$src\witsml_result.txt" "$dest\wpctt_witsml_result_$stamp.txt" -Force

# Hashear solo los artefactos de esta ejecución para no invalidar
# manifiestos anteriores.
$files = Get-ChildItem $dest -File |
  Where-Object { $_.LastWriteTime.Date -eq (Get-Date).Date } |
  Sort-Object Name
$files | ForEach-Object {
  "{0}  results/{1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
} | Set-Content "certification/manifests/wpctt_$stamp.sha256" -Encoding ascii
```

Antes de archivar, comprobar que el log no contiene `!*** FAILURE` y contar los
scripts terminados:

```powershell
$log = "certification/results/log_<fecha>.txt"
(Select-String $log -Pattern '^!\*\*\* FAILURE').Count
Get-Content $log | Select-String "completed: (Pass|Fail|Skipped)" |
  ForEach-Object { ($_.Line -split ': ')[-1] } | Group-Object | Format-Table
```

### 5.1 Manifiesto de la suite instalada (criterio 33)

El expediente incluye el hash de cada archivo instalado y un hash agregado:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\certification\generar_manifiesto_suite.ps1 `
  -ToolHome "D:\Descargas-J\Docs\wPCTT1.1-t1.0-s1.0"
```

El script escribe `certification/manifests/suite_<aaaaMMdd>.sha256` con una
línea `<sha256>  <ruta relativa>` por archivo, en orden, y una última línea
`# aggregate-sha256: <hash>`. El hash agregado es el SHA-256 de esas líneas
ordenadas. Se excluyen `results/` y `server/backup-*/`; no se modifica ningún
script, WSDL ni XSD oficial.

## 6. Evidencia archivada

| Ejecución | Suite | Duración | Scripts | Fallos | Resultado |
| --- | --- | --- | --- | --- | --- |
| `log_20261103153118`<br>(2026-11-03 15:31, hora local de la herramienta) | `wPCTT1.1-t1.0-s1.0` / `testsuite` | 82 min 10 s | 75 pass, 0 skipped | 0 | `!*** SUCCESS` |
| `log_20261103134009`<br>(2026-11-03 13:40, hora local de la herramienta) | `wPCTT1.1-t1.0-s1.0` / `testsuite` | 82 min 35 s | 74 pass, 1 skipped | 0 | `!*** SUCCESS` (histórica) |
| `log_20261101203643`<br>(2026-11-01 20:36, hora local de la herramienta) | `wPCTT1.1-t1.0-s1.0` / `testsuite` | 79 min 42 s | 70 pass, 6 skipped | 0 | `!*** SUCCESS` (histórica) |

La ejecución del **2026-11-03 15:31** es la que certifica la configuración
publicada: `maxDataPoints` 3 000 000, `growingTimeoutPeriod` 3 600 s,
`changeDetectionPeriod` 60 s (D-17), respuestas gzip según `Accept-Encoding`
sin `compressionMethod` en `GetCap` (D-01), `cascadedDelete=true` publicado y
soportado, y `mudLog` como objeto de primera clase. La suite ejecuta y aprueba
`test22`, `test34`, `test61`, `test63`, `test92b` y `test94e`. Se ejecutó con el
dataset estándar recién cargado y con `data_grower_script` publicando en
`Energistics-w1-wb1-log-0001` y `Energistics-w1-wb1-trajectory-0001` durante
toda la suite.

No quedan scripts omitidos. La ejecución del 2026-11-03 13:40 se conserva como
evidencia histórica previa a `cascadedDelete` (omitía `test22`), y la del
2026-11-01 como evidencia previa a `mudLog`; en esta última los 6 scripts
omitidos correspondían a objetos fuera del alcance 1.0.3.

Artefactos de la ejecución vigente y manifiestos locales (ignorados por Git):

- `certification/results/log_20261103153118.txt`
  — `37be5151d06b1eebde6cd5ff78de4878793253853ac3cc49d32e0bbc6163e2c6`
- `certification/results/log_20261103153118_soap.txt`
  — `0e943e49d794df19326fb8f9bc5b7675948b5619defa7dfc96d3badf5de2026a`
- `certification/results/wpctt_witsml_result_20261103153118.txt`
  — `6d7ece3d866c61785bf99a8684040ed7631a2330cb674c515136f57957349399`
- `certification/manifests/wpctt_20261103153118.sha256`
- `certification/manifests/suite_20261103153118.sha256`
  (4 179 archivos, `# aggregate-sha256:
  25a88acc328a35d355a1fd76e361a8276d1168535339623d61a7762f2bc09f0d`)

Evidencia histórica del 2026-11-03 13:40:

- `certification/results/log_20261103134009.txt`
  — `e656281a9193a09b61ade13919466e9318133bd224182b392f406b937579adc5`
- `certification/results/log_20261103134009_soap.txt`
  — `9310eabb3e0a52c3464c520157518271e3a88fff83eea2e3dc91193e2bea3865`
- `certification/results/wpctt_witsml_result_20261103.txt`
  — `674455f910ac34c00a67e925258221f04b411428246b18407ef34f4d438e2698`
- `certification/manifests/wpctt_20261103.sha256`
- `certification/manifests/suite_20261103.sha256`

Evidencia histórica del 2026-11-01:

- `certification/results/log_20261101203643.txt`
  — `2b8390ab588dac1d401d064812f7c3a6168e6c3caeac99aa7e18719546890531`
- `certification/results/log_20261101203643_soap.txt`
  — `164a7244f639873c662c5dba713a4b041358f95cb1b4d17cfca6fd01cb7df75f`
- `certification/results/wpctt_witsml_result.txt`
  — `2178c03876f2f1d64fe685b463a29924ea1570072a204b79db45f3a2aa9c0ee3`
- `certification/manifests/wpctt_20261101.sha256`

### 6.1 `changeDetectionPeriod`: 60 s frente a 600 s

El expediente contiene dos valores para esta capacidad:

- **D-17** (decisión aprobada) fija `changeDetectionPeriod` en **60 s**.
- La tabla de «Valores de GetCap» (línea 278) anota junto a ese mismo valor
  «Debe ser = 600 s; se valida con la prueba de polling (485)».

Gobierna **D-17**, porque es la decisión cerrada y la que se aplicó a
`server_config` y a los valores por defecto del producto. La suite oficial no
fija un umbral: los scripts `test61`, `test78`, `test79a`, `test79b` y `test80`
esperan `changeDetectionPeriod + 1` segundos antes de consultar el `changeLog`,
de modo que cualquier valor declarado es coherente mientras el servidor lo
respete. Declarar 60 s ahorra ~117 minutos de espera (13 pausas) sin alterar la
semántica. Si en la evaluación formal se exige el valor de 600 s, basta
actualizar `server_config.change_detection_seconds` (o el valor por defecto de
`ServerConfig`) y repetir la suite: no hay cambios de código asociados.

### 6.2 Pruebas propias D-15 y criterios 12, 13, 19, 29 y 36

Además de la suite oficial, el expediente incluye pruebas automatizadas para los
MUST que la herramienta no ejecuta. La trazabilidad completa está en
`docs/adr/0007-pruebas-propias-d15.md`; el resumen es:

| Test Plan / criterio | Prueba | Evidencia |
| --- | --- | --- |
| 12 y 13 | `test_d15_12_13_change_log_keeps_update_and_delete_entries` | Entradas `update` y `delete` consultables con el filtro SQ-018. |
| 74 y 75 | `test_d15_74_*`, `test_d15_75_*` | Truncamiento por `maxDataNodes` y `maxDataPoints` con código `+2`, sin duplicados. |
| 76c | `test_d15_76c_request_latest_values_for_decreasing_log` | Últimos valores de un log descendente y rechazo `-1054` fuera de límite. |
| 82 | `test_d15_82_log_append_and_intersection_clearing_behavior` | *Clearing behavior* de la API §6.7.4.6 y criterio 12. |
| 83 y criterio 19 | `test_wmls_gzip_responses` | Gzip de respuesta, `Vary` y rechazo de identidad. |
| 84 | `test_d15_84_client_compression_is_not_advertised` | Sin `compressionMethod` en `GetCap`; solicitud comprimida con fault 400. |
| 6, 7 y 19 | Pruebas existentes de `GetCap` e `id-only` | Capacidades publicadas y consultas de identificación. |
| 22 | Prueba oficial `test22` + `test_wmls_cascaded_delete_removes_descendants` | `cascadedDelete=true` elimina `well -> wellbore -> log/trajectory/mudLog` y registra un `delete` por objeto. |
| `-432` | `test_wmls_discovery_and_crud` + `test_wmls_cascaded_delete_removes_descendants` | Sin `cascadedDelete=true`, el padre con hijos se rechaza con `-432`. |
| `-427` y `-428` | `test_wmls_request_object_selection_option_rules` | `requestObjectSelectionCapability` distinto de `none` es el único keyword permitido y exige la Minimum Query Template; `none` restaura el comportamiento normal. |
| `-443` y `-453` | `test_wmls_uom_dictionary_validation` + `test_uom_dictionary_validation_follows_measure_types` | Medida sin `uom` (`-453`) o con un valor que no es `annotation` del diccionario oficial (`-443`), con resolución del tipo XSD de cada elemento. |
| Criterio 13 | `test_acceptance_13_index_type_and_duplicate_nodes` | Tipo de índice preservado y duplicados rechazados con `-463`. |
| Criterio 29 | `test_acceptance_29_soap_and_rest_share_use_cases` (×4) | Lectura por REST de un alta SOAP y borrado REST visible por SOAP. |

El diccionario de unidades vendorizado
(`schemas/witsml/1.4.1.1/witsml_v1.4.1.1_data/ancillary/witsmlUnitDict.xml`,
700 052 bytes) tiene SHA-256
`4475747828d983b8cfc5a7a7cf4e47a219bdd2cf49cc8a204cd1ba487f08bbaa`, idéntico al
archivo distribuido por Energistics.

La retención de 24 h de las pruebas 12 y 13 no se espera: D-10 fija 5 años sin
purga, así que la prueba comprueba que la entrada sigue consultable con el mismo
filtro. El *clearing* por canal se implementó en
`WitsmlApplicationService._clear_updated_channels` y el transporte SOAP ahora
devuelve un fault 400 ante un cuerpo ilegible o comprimido.

## 7. Triaje

Clasificar cada fallo antes de tocar código:

- **Contrato**: WSDL, namespace, SOAPAction, `OptionsIn`, `ReturnValueIn`.
- **Esquema**: XML de entrada o salida que no valida contra el XSD oficial.
- **Comportamiento**: código WMLS, permisos, crecimiento, truncamiento,
  concurrencia o borrado.
- **Dataset**: el objeto de prueba no existe o no tiene los valores que espera
  el script.

No se modifican los scripts oficiales ni los XSD. Cada corrección debe ir
acompañada de una prueba propia que reproduzca el caso y de una nueva ejecución
completa de la suite.

## Criterio de cierre

- Suite ejecutada de principio a fin sin fallos.
- `results/` y manifiesto de hashes archivados como evidencia.
- ADR/README actualizados si cambia una decisión de contrato.
- Release `1.0.3` etiquetado y expediente listo para la evaluación formal.

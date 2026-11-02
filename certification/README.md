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
$src  = "D:\Descargas-J\Docs\wPCTT1.1-t1.0-s1.0\results"
$dest = "certification/results"
New-Item -ItemType Directory -Force -Path $dest, "certification/manifests" | Out-Null
Copy-Item "$src\log_2026*.txt" -Exclude "*_soap.txt" $dest -Force
Copy-Item "$src\log_2026*_soap.txt" $dest -Force
Copy-Item "$src\witsml_result.txt" "$dest\wpctt_witsml_result.txt" -Force

$stamp = Get-Date -Format "yyyyMMdd"
Get-ChildItem $dest -File | Sort-Object Name | ForEach-Object {
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

## 6. Evidencia archivada

| Ejecución | Suite | Duración | Scripts | Fallos | Resultado |
| --- | --- | --- | --- | --- | --- |
| `log_20261101203643`<br>(2026-11-01 20:36, hora local de la herramienta) | `wPCTT1.1-t1.0-s1.0` / `testsuite` | 79 min 42 s | 70 pass, 6 skipped | 0 | `!*** SUCCESS` |

Esta ejecución es la que certifica la configuración publicada: `maxDataPoints`
3 000 000, `growingTimeoutPeriod` 3 600 s, `changeDetectionPeriod` 60 s
(D-17) y respuestas gzip según `Accept-Encoding`, sin `compressionMethod` en
`GetCap` (D-01). Se ejecutó con el dataset estándar recién cargado y con
`data_grower_script` publicando en `Energistics-w1-wb1-log-0001` y
`Energistics-w1-wb1-trajectory-0001` durante toda la suite.

Los 6 scripts omitidos corresponden a objetos fuera del alcance 1.0.3
(`mudLog` y afines) que la suite salta por capacidades no declaradas. Artefactos
y manifiesto local (ignorados por Git):

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

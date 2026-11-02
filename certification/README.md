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

| Fecha (UTC) | Suite | Scripts | Fallos | Resultado |
| --- | --- | --- | --- | --- |
| 2026-11-01 20:12 | `wPCTT1.1-t1.0-s1.0` / `testsuite` | 70 pass, 6 skipped | 0 | `!*** SUCCESS` |

Los 6 scripts omitidos corresponden a objetos fuera del alcance 1.0.3
(`mudLog` y afines) que la suite salta por capacidades no declaradas. Artefactos
y manifiesto local (ignorados por Git):

- `certification/results/log_20261101201203.txt`
  — `d8bd3d0f1d02d6b56ff8c7c7cd617f12b14b390cefe932352b52871d911aafee`
- `certification/results/log_20261101201203_soap.txt`
  — `7b72cb174f476f71b4d6ccc00499a805d4a1ae0d5d6c537adfc42703a4fe2f2b`
- `certification/results/wpctt_witsml_result.txt`
  — `a3e3e8e7977d67aacc5704de5ddeb12ad007df35eba13299340883731a15af7c`
- `certification/manifests/wpctt_20261101.sha256`

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

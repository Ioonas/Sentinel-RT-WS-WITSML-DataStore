<#
.SYNOPSIS
    Genera el manifiesto SHA-256 de la suite oficial wPCTT instalada.

.DESCRIPTION
    Recorre la instalacion de wPCTT1.1-t1.0-s1.0 y escribe una linea por archivo
    con el formato ``<sha256>  <ruta relativa>``. Al final anade el hash
    agregado, calculado como SHA-256 de todas las lineas ordenadas
    (concatenadas con salto de linea y terminadas en salto de linea).

    Se excluyen ``results/`` (cambia en cada ejecucion) y las copias de
    seguridad ``server/backup-*/`` creadas por ``prepare_wcat.py``. No se
    modifican los scripts, el WSDL ni los XSD oficiales.

.PARAMETER ToolHome
    Ruta de la herramienta oficial. Por defecto usa ``SENTINEL_WPCTT_DIR``.

.PARAMETER Output
    Archivo de salida. Por defecto
    ``certification/manifests/suite_<aaaaMMdd>.sha256``.

.EXAMPLE
    .\certification\generar_manifiesto_suite.ps1 `
        -ToolHome "D:\Descargas-J\Docs\wPCTT1.1-t1.0-s1.0"
#>
[CmdletBinding()]
param(
    [string]$ToolHome = $env:SENTINEL_WPCTT_DIR,
    [string]$Output
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ToolHome)) {
    throw "Indica -ToolHome o define SENTINEL_WPCTT_DIR."
}
if (-not (Test-Path -LiteralPath $ToolHome -PathType Container)) {
    throw "No se encontro la instalacion de wPCTT en '$ToolHome'."
}
$ToolHome = (Resolve-Path -LiteralPath $ToolHome).Path

if ([string]::IsNullOrWhiteSpace($Output)) {
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd")
    $Output = Join-Path $PSScriptRoot "manifests\suite_$stamp.sha256"
}
$outputDirectory = Split-Path -Parent $Output
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$entries = Get-ChildItem -LiteralPath $ToolHome -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($ToolHome.Length + 1).Replace("\", "/")
    if ($relative -match "(^|/)results(/|$)") { return }
    if ($relative -match "^server/backup-[^/]+/") { return }
    [pscustomobject]@{
        Relative = $relative
        Hash     = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()
    }
} | Sort-Object -Property Relative

$lines = @($entries | ForEach-Object { "{0}  {1}" -f $_.Hash, $_.Relative })
if ($lines.Count -eq 0) {
    throw "La instalacion '$ToolHome' no contiene archivos que hashear."
}

$aggregateText = ($lines -join "`n") + "`n"
$sha256 = [System.Security.Cryptography.SHA256]::Create()
try {
    $aggregateBytes = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($aggregateText))
} finally {
    $sha256.Dispose()
}
$aggregate = -join ($aggregateBytes | ForEach-Object { $_.ToString("x2") })

$header = @(
    "# Suite: wPCTT1.1-t1.0-s1.0"
    "# Instalacion: $ToolHome"
    "# Generado: $((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))"
    "# Archivos: $($lines.Count)"
    "# Hash agregado: SHA-256 de las lineas ordenadas de este manifiesto"
)
$footer = "# aggregate-sha256: $aggregate"

$content = ($header + $lines + $footer -join "`n") + "`n"
[System.IO.File]::WriteAllText($Output, $content, (New-Object System.Text.UTF8Encoding($false)))

Write-Output "Manifiesto: $Output"
Write-Output "Archivos: $($lines.Count)"
Write-Output "Hash agregado: $aggregate"

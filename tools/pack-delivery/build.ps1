# Build the installable add-on zip (dist\superdna_pack_delivery-<version>.zip).
param(
    [string]$Blender = 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe'
)
$Here = $PSScriptRoot
$Source = Join-Path $Here 'superdna_pack_delivery'
$Dist = Join-Path $Here 'dist'

if (-not (Test-Path -LiteralPath $Blender)) {
    Write-Host "Blender not found: $Blender (pass -Blender <path to blender.exe>)"
    exit 1
}

New-Item -ItemType Directory -Force $Dist | Out-Null
& $Blender --factory-startup --command extension build --source-dir $Source --output-dir $Dist
if ($LASTEXITCODE -ne 0) {
    Write-Host "Blender extension build failed"
    exit 1
}
Get-ChildItem -LiteralPath $Dist -Filter '*.zip' | ForEach-Object { Write-Host "Built $($_.FullName)" }

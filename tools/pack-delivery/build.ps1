# Build the installable add-on zip (dist\superdna_pack_delivery-<version>.zip) with the head model inside.
# NewHead.fbx is not kept in git; pass its path with -HeadFbx.
param(
    [string]$HeadFbx = 'D:\SuperDNA\NewHead.fbx',
    [string]$Blender = 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe'
)
$Here = $PSScriptRoot
$Source = Join-Path $Here 'superdna_pack_delivery'
$Dist = Join-Path $Here 'dist'

if (-not (Test-Path -LiteralPath $HeadFbx)) {
    Write-Host "Head model not found: $HeadFbx (pass -HeadFbx <path>)"
    exit 1
}
if (-not (Test-Path -LiteralPath $Blender)) {
    Write-Host "Blender not found: $Blender (pass -Blender <path to blender.exe>)"
    exit 1
}

# Build from a staging copy so the head never lands in the source folder
$Stage = Join-Path ([System.IO.Path]::GetTempPath()) ('pack_delivery_' + [guid]::NewGuid())
$StageSource = Join-Path $Stage 'superdna_pack_delivery'
New-Item -ItemType Directory -Force $StageSource | Out-Null
try {
    Get-ChildItem -LiteralPath $Source -File | Where-Object { $_.Extension -ne '.pyc' } |
        Copy-Item -Destination $StageSource
    Copy-Item -LiteralPath $HeadFbx -Destination (Join-Path $StageSource 'NewHead.fbx')
    New-Item -ItemType Directory -Force $Dist | Out-Null
    & $Blender --factory-startup --command extension build --source-dir $StageSource --output-dir $Dist
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Blender extension build failed"
        exit 1
    }
} finally {
    Remove-Item -Recurse -Force -LiteralPath $Stage
}
Get-ChildItem -LiteralPath $Dist -Filter '*.zip' | ForEach-Object { Write-Host "Built $($_.FullName)" }

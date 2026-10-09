# One-time setup: creates a Python virtual environment and installs requirements.
$Here = $PSScriptRoot
$Venv = Join-Path $Here '.venv'
$Req  = Join-Path $Here 'universal-spp\requirements.txt'

if (-not (Test-Path -LiteralPath $Req)) {
    Write-Host "requirements.txt not found at $Req"
    exit 1
}

# Try uv first, then fall back to py -3 or python
$Python = $null
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "Creating venv with uv..."
    uv venv --python 3.12 "$Venv"
    if ($LASTEXITCODE -ne 0) { Write-Host "uv venv failed"; exit 1 }
    uv pip install --python "$Venv\Scripts\python.exe" -r $Req
    if ($LASTEXITCODE -ne 0) { Write-Host "uv pip install failed"; exit 1 }
} else {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $Python = 'py'
    } else {
        $Python = 'python'
    }
    Write-Host "Creating venv with $Python..."
    & $Python -m venv "$Venv"
    if ($LASTEXITCODE -ne 0) { Write-Host "venv creation failed"; exit 1 }
    & "$Venv\Scripts\python.exe" -m pip install -r $Req
    if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed"; exit 1 }
}

Write-Host "Ready. Double-click SppDowngrader.bat."

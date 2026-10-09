# Build SppDowngrader.exe using PyInstaller
$Here = $PSScriptRoot
$Venv = Join-Path $Here '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$Spec = Join-Path $Here 'SppDowngrader.spec'
$Setup = Join-Path $Here 'setup.ps1'

# Ensure venv exists
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Python venv not found. Running setup.ps1..."
    & $Setup
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Setup failed"
        exit 1
    }
}

# Install PyInstaller, tkinterdnd2 and sv-ttk (Windows 11 theme)
Write-Host "Installing PyInstaller, tkinterdnd2 and sv-ttk..."
if (Get-Command uv -ErrorAction SilentlyContinue) {
    & uv pip install --python $VenvPython pyinstaller tkinterdnd2 sv-ttk
} else {
    & $VenvPython -m pip install pyinstaller tkinterdnd2 sv-ttk
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "Dependency install failed"
    exit 1
}

# Build the exe
Write-Host "Building SppDowngrader.exe..."
Push-Location $Here
& $VenvPython -m PyInstaller $Spec --noconfirm --distpath (Join-Path $Here 'dist') --workpath (Join-Path $Here 'build')
Pop-Location

if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller build failed"
    exit 1
}

$ExePath = Join-Path $Here 'dist\SppDowngrader.exe'
if (Test-Path -LiteralPath $ExePath) {
    $Size = [math]::Round((Get-Item $ExePath).Length / 1MB, 1)
    Write-Host "Success! $ExePath ($Size MB)"
    exit 0
} else {
    Write-Host "Exe not found after build"
    exit 1
}

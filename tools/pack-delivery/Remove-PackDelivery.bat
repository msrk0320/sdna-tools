@echo off
rem Removes every installed copy of the SuperDNA Pack Delivery add-on from all Blender versions
rem (extensions and legacy add-ons), so a fresh version can be installed. Nothing else is touched.
setlocal enabledelayedexpansion

tasklist /FI "IMAGENAME eq blender.exe" 2>nul | find /I "blender.exe" >nul
if not errorlevel 1 (
    echo Blender is open. Close every Blender window, then run this again.
    pause
    exit /b 1
)

set "ROOT=%APPDATA%\Blender Foundation\Blender"
set FOUND=0

for /d %%V in ("%ROOT%\*") do (
    for /d %%R in ("%%V\extensions\*") do (
        for /d %%A in ("%%R\superdna_pack_delivery*") do (
            echo Removing %%A
            rmdir /s /q "%%A"
            set FOUND=1
        )
    )
    for /d %%A in ("%%V\scripts\addons\superdna_pack_delivery*") do (
        echo Removing %%A
        rmdir /s /q "%%A"
        set FOUND=1
    )
)

echo.
if !FOUND!==1 (
    echo Done. Pack Delivery is removed. Open Blender and install the new zip.
) else (
    echo No Pack Delivery add-on found in "%ROOT%".
)
pause

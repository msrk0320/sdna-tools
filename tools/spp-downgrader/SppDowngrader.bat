@echo off
rem Double-click to open, or drag a .spp/.uspp onto this file.
start "" powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0SppDowngrader.ps1" "%~1"

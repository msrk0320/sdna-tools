# SPP Downgrader

Drag-and-drop converter that rebuilds a Substance 3D Painter .spp/.uspp for an older Painter version.

## Portable exe (recommended)

`SppDowngrader.exe` is a single file with everything bundled - no Python or install needed. Double-click it, or drag a .spp/.uspp onto it. Build it with:

```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1   # -> dist\SppDowngrader.exe
```

Headless: `SppDowngrader.exe --convert IN --target 11 -o OUT.spp --yes`.

The `SppDowngrader.bat` + `setup.ps1` route below runs the same tool from source.

## Setup

Requires Python 3.11+ or `uv`.

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

## Usage

Double-click `SppDowngrader.bat` or drag a .spp/.uspp onto it. In the window:
1. Drop a file in the input area (or click to browse)
2. Pick a target Painter version (defaults to one below the source)
3. Click Convert
4. Confirm the loss warning if the downgrade is lossy

Output is saved next to the input as `<name>_v<target>.spp`. The original file is never modified. Close Painter fully before opening the new file.

## Engine

Universal SPP (MIT, unofficial, not affiliated with Adobe) is vendored in `universal-spp/`. Update it with:

```sh
git subtree pull --prefix tools/spp-downgrader/universal-spp https://github.com/Yeusepe/Universal-Painter-Files main --squash
```

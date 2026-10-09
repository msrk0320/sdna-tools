# SPP Downgrader

Drag-and-drop converter that rebuilds a Substance 3D Painter .spp/.uspp for an older Painter version.

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

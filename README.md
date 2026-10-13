# SDNA Tools

Small Windows tools for 3D texturing work with Adobe Substance 3D Painter and Blender.

## Download

Ready-to-run builds are on the [Releases](../../releases) page. Each tool is a single portable `.exe`: no install, no Python needed.

## Tools

| Tool | Description |
|------|-------------|
| `tools/spp-downgrader` | Drag-and-drop converter that rebuilds a Substance 3D Painter .spp/.uspp for an older Painter version. Portable single-file exe (see Releases). |
| `tools/pack-delivery` | Blender add-on that packs a finished eyewear task into a versioned `FinalDelivery\<SKU>_vN` folder (packed .blend, GLB, SPP, overlays, head shots). Install zip on Releases. |
| Painter Live View | Substance 3D Painter panel that shows your textures in the client viewer's exact render, live while you paint, following Painter's camera. Installer on Releases (installer only, no source here). |

## Adding a tool

Put it in `tools/<name>/` with its own README.md and a setup script if it needs dependencies. Never commit client files (.spp, .uspp, .glb, .fbx), virtual environments, browser profiles or data folders — .gitignore blocks the common ones. This repo is public.

## Notice

These tools are unofficial and not affiliated with or endorsed by Adobe. `spp-downgrader` uses the [Universal SPP](https://github.com/Yeusepe/Universal-Painter-Files) engine (MIT, see its LICENSE and NOTICE in `tools/spp-downgrader/universal-spp/`).

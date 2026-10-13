# Pack Delivery (Blender add-on)

Blender 4.5+ add-on that packs a finished eyewear texturing task into a versioned client delivery folder next to the open .blend:

```
<task folder>\
  <TaskID>.blend
  FinalDelivery\
    <SKU>_v1\   <SKU>.blend (textures packed inside), <SKU>.glb, <SKU>.spp,
                Overlay.png (or Overlay_01.png, Overlay_02.png, ...),
                Head Postion_01.png (profile), Head Postion_02.png (front)
    <SKU>_v2\   ...
```

Every Pack writes the next version and keeps the earlier ones. The head model used for the head-overlay renders ships inside the add-on.

## Install
1. Download `superdna_pack_delivery-<version>.zip` from [Releases](https://github.com/msrk0320/sdna-tools/releases).
2. Blender > Edit > Preferences > Get Extensions > drop-down (top right) > **Install from Disk**, pick the zip.

## Use (3D View > N panel > SuperDNA > Pack Delivery)
1. Open and save the final `<TaskID>.blend`.
2. **Detect** fills SKU, task ID, GLB, SPP, Textures folder, every overlay in the task folder and the Head overlay folder.
   Use **+** (Shift/Ctrl-click several files) or the arrow menu to add overlays, **X** to drop one.
3. **Capture Head Overlays** renders the product on the head, front and profile, into `<task>\HeadOverlay\`.
4. **Preview** lists errors, warnings and what will be delivered, and the target `FinalDelivery\<SKU>_v<N>`.
5. **Pack** writes that version and opens it. A `pack_report_<time>.txt` is left in the task folder.

Working-file names: the .blend, GLB and SPP may be named `<TaskID>`, `<TaskID>_<SKU>` or `<SKU>`, each optionally followed by
`_v1`, `_r1`, `_rev1`, `_ver1`, `_final` or `_fix` (also stacked, e.g. `_v2_final`). When several versions exist, Detect picks the
highest number. Delivered files are always named after the SKU.

Expected inputs: one material on the meshes named `Mat_<SKU>`, and Painter's export in `<spp name>\Textures\` with `Mat_<SKU>_BaseColor.png`, `_Roughness.png` (required) and `_Metallic`, `_Normal`, `_Transmissive` (optional).

## Build
```
powershell -ExecutionPolicy Bypass -File build.ps1 -HeadFbx <path to NewHead.fbx>
```
The head model is not kept in git; the script copies it into the zip. Output: `dist\superdna_pack_delivery-<version>.zip`.

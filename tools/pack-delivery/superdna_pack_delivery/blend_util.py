"""Blender-side helpers for Pack Delivery (facts from the open file, packed copy)."""

import os
import re
import subprocess

import bpy

try:
    from . import core
except ImportError:  # imported as a plain module by pack_blend.py and tests
    import core

LAST_LOG = ""
NO_WINDOW = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


def materials_in_use():
    names = []
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH":
            continue
        for slot in ob.material_slots:
            if slot.material and slot.material.name not in names:
                names.append(slot.material.name)
    return names


def find_material(sku):
    for name in materials_in_use():
        if core.sku_from_material(name) == sku:
            return bpy.data.materials[name]
    return None


def wired_images(mat):
    found = []

    def visit(tree):
        for node in tree.nodes:
            if node.type == "TEX_IMAGE" and node.image and node.image not in found:
                found.append(node.image)
            elif node.type == "GROUP" and node.node_tree:
                visit(node.node_tree)

    if mat and mat.use_nodes and mat.node_tree:
        visit(mat.node_tree)
    return found


def _abspath(image):
    return os.path.normpath(bpy.path.abspath(image.filepath, library=image.library))


def _stem_suffix(stem, sku):
    m = re.match(r"^Mat_%s_(%s)$" % (re.escape(sku), "|".join(core.MAP_SUFFIXES)), stem, re.IGNORECASE)
    if not m:
        return None
    return next(s for s in core.MAP_SUFFIXES if s.lower() == m.group(1).lower())


def map_suffix(image, sku):
    if not image.filepath:
        return None
    return _stem_suffix(os.path.splitext(os.path.basename(_abspath(image)))[0], sku)


def packed_images(mat):
    return [img for img in wired_images(mat) if img.packed_file]


def packed_map_suffixes(mat, sku):
    """Map suffixes of the packed SKU images, by file name or, failing that, by image name."""
    out = []
    for img in packed_images(mat):
        suffix = map_suffix(img, sku) or _stem_suffix(os.path.splitext(img.name)[0], sku)
        if suffix and suffix not in out:
            out.append(suffix)
    return out


def sku_image_dirs(mat, sku):
    dirs = []
    for img in wired_images(mat):
        if map_suffix(img, sku):
            d = os.path.dirname(_abspath(img))
            if d not in dirs:
                dirs.append(d)
    return dirs


def missing_images(mat, sku):
    """Wired, unpacked non-SKU images whose file is gone; packing them would fail."""
    out = []
    for img in wired_images(mat):
        if img.source == "FILE" and img.filepath and not img.packed_file and not map_suffix(img, sku):
            path = _abspath(img)
            if not os.path.isfile(path) and path not in out:
                out.append(path)
    return out


def _run_background(blend, script, args, timeout):
    """Run <script> (next to this file) in a background Blender on <blend>; its output goes to LAST_LOG."""
    global LAST_LOG
    cmd = [bpy.app.binary_path, "--background", "--factory-startup", blend,
           "--python", os.path.join(os.path.dirname(os.path.abspath(__file__)), script), "--", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise core.PackError("Background Blender took longer than %d s." % timeout)
    LAST_LOG = (proc.stdout or "") + (proc.stderr or "")
    return proc


def make_packed_blend(staging, sku, expected, packed=False, timeout=120):
    """Save a copy of the open file into staging and pack it in a background Blender.

    packed: the maps are already packed in the .blend; keep them instead of relinking to Texture\\.
    """
    global LAST_LOG
    LAST_LOG = ""
    path = os.path.join(staging, sku + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True, relative_remap=True)
    texture_dir = "" if packed else os.path.join(staging, core.PACK_DIR)
    proc = _run_background(path, "pack_blend.py", [sku, texture_dir], timeout)
    core.check_packed(proc.stdout, proc.returncode, expected)


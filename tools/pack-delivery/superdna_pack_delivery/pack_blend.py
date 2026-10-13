"""Run by background Blender on the staged copy: drop the Live View workspace, the job profile and the legacy flip
markers, purge unused data, relink SKU maps to Texture\\, pack wired images and every other resource, save.
An empty <texture_dir> means the maps are already packed: they are kept as they are, not relinked.

Usage: blender --background --factory-startup <staged.blend> --python pack_blend.py -- <sku> <texture_dir>
Prints PURGED:<removed data-blocks>, PACKERROR: <reason> per problem and, once the SKU material is found, exactly one
line PACKED:<packed>/<wired>.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import blend_util  # noqa: E402
import core  # noqa: E402


LIVE_WORKSPACES = ("Live View", "ShopAR")  # "ShopAR" is the Live View workspace's name before MadPlugin 1.12


def drop_live_workspace():
    """The Live View workspace is the artist's own tool: not part of a delivery."""
    gone = [bpy.data.workspaces[n] for n in LIVE_WORKSPACES if n in bpy.data.workspaces]
    if not gone:
        return
    other = next((w for w in bpy.data.workspaces if w not in gone), None)
    for win in bpy.context.window_manager.windows:
        if win.workspace in gone and other is not None:
            win.workspace = other
    bpy.data.batch_remove(gone)


def drop_job_profile():
    """The job profile is MadPlugin's own data: the client never gets it."""
    for scene in bpy.data.scenes:
        scene.pop("madplugin_profile", None)


def drop_flip_markers():
    """Strip flip marks: .blend files may carry per-face flip markers used during modelling. The client gets the
    final flipped faces, not the marker attribute or scene toggle state."""
    for mesh in bpy.data.meshes:
        attr = mesh.attributes.get("madplugin_flip")
        if attr is not None:
            mesh.attributes.remove(attr)
    for scene in bpy.data.scenes:
        scene.pop("madplugin_flips_off", None)


def finish(images):
    """Pack every other resource, save without a .blend1 and report PACKED:<packed>/<wired>."""
    packed = sum(1 for img in images if img.packed_file)
    try:
        bpy.ops.file.pack_all()  # everything else the purged file still uses (other images, fonts, sounds)
    except RuntimeError as e:
        print("PACKERROR: pack all resources: %s" % e)
    bpy.context.preferences.filepaths.save_version = 0  # never leave a <SKU>.blend1 in the delivery
    bpy.ops.wm.save_mainfile()
    leftover = bpy.data.filepath + "1"
    if os.path.exists(leftover):
        os.remove(leftover)
    print("PACKED:%d/%d" % (packed, len(images)))
    return 0


def main(sku, texture_dir):
    drop_live_workspace()
    drop_flip_markers()
    drop_job_profile()
    purged = bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    print("PURGED:%d" % purged)
    mat = blend_util.find_material(sku)
    if mat is None:
        print("PACKERROR: no material for SKU %s" % sku)
        return 2
    images = blend_util.wired_images(mat)
    for img in images:
        suffix = blend_util.map_suffix(img, sku)
        if suffix and texture_dir:
            name = "%s_%s.png" % (sku, core.DELIVERED_NAMES[suffix])
            if os.path.isfile(os.path.join(texture_dir, name)):
                img.filepath = "//%s/%s" % (core.PACK_DIR, name)
                img.reload()
            else:
                print("PACKERROR: %s missing in %s" % (name, texture_dir))
        elif img.packed_file:
            continue  # already inside the .blend
        try:
            img.pack()
        except RuntimeError as e:
            print("PACKERROR: %s: %s" % (img.name, e))
    return finish(images)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    sys.exit(main(*args))

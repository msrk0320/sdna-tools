"""Run by background Blender on a throwaway copy of the open file: import the head, size it to the product,
render the front (orthographic) and profile (perspective) head overlays. Never saves.

Usage: blender --background --factory-startup <copy.blend> --python head_capture.py -- <head.fbx> <out_dir> <sku>
Prints HEADSCALE:<factor> and one HEADSHOT:<view>:<png path> per view, or HEADERROR: <reason>.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
import core  # noqa: E402

SIZE = 1600         # px, square
LENS = 50.0         # mm, profile camera
SENSOR = 36.0       # mm
MARGIN = 1.15       # frame the head with this much room
BACKGROUND = (0.05, 0.05, 0.05)
HEAD_COLOR = (0.8, 0.8, 0.8)


def world_bbox(objects):
    pts = [o.matrix_world @ Vector(c) for o in objects if o.type == "MESH" for c in o.bound_box]
    if not pts:
        return None
    return (Vector([min(p[i] for p in pts) for i in range(3)]),
            Vector([max(p[i] for p in pts) for i in range(3)]))


def import_head(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def scale_about_origin(objects, factor):
    for o in objects:
        if o.parent is None or o.parent not in objects:
            o.location *= factor
            o.scale *= factor
    bpy.context.view_layer.update()


def add_camera(scene, name, location, target, ortho_scale=None):
    cam = bpy.data.cameras.new(name)
    ob = bpy.data.objects.new(name, cam)
    scene.collection.objects.link(ob)
    ob.location = location
    ob.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()
    if ortho_scale:
        cam.type = "ORTHO"
        cam.ortho_scale = ortho_scale
    else:
        cam.lens, cam.sensor_width = LENS, SENSOR
    distance = (target - location).length
    cam.clip_start, cam.clip_end = distance * 0.01, distance * 10
    return ob


def setup_render(scene):
    r = scene.render
    r.engine = "BLENDER_WORKBENCH"
    r.resolution_x = r.resolution_y = SIZE
    r.resolution_percentage = 100
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.color_type = "SINGLE"
    shading.single_color = HEAD_COLOR
    shading.show_object_outline = True
    if scene.world is None:
        scene.world = bpy.data.worlds.new("HeadCapture")
    scene.world.color = BACKGROUND


def render(scene, camera, path):
    scene.camera = camera
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main(head_fbx, out_dir, sku):
    scene = bpy.context.scene
    product = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
    box = world_bbox(product)
    if box is None:
        print("HEADERROR: the scene has no product mesh to measure.")
        return 1
    frame_width = box[1].x - box[0].x
    head = import_head(head_fbx)
    head_box = world_bbox(head)
    if head_box is None:
        print("HEADERROR: %s has no mesh." % head_fbx)
        return 1
    factor = core.head_scale_factor(head_box[1].x - head_box[0].x, frame_width)
    if factor != 1.0:
        scale_about_origin(head, factor)
        head_box = world_bbox(head)
    lo, hi = head_box
    problem = core.head_fit_problem(hi.x - lo.x, frame_width)
    if problem:
        print("HEADERROR: %s" % problem)
        return 1
    print("HEADSCALE:%g" % factor)

    setup_render(scene)
    size, centre = hi - lo, (lo + hi) / 2
    front_dist = size.y * 2
    front = add_camera(scene, "HeadFront", Vector((centre.x, lo.y - front_dist, centre.z)),
                       Vector((centre.x, lo.y, centre.z)), ortho_scale=max(size.x, size.z) * MARGIN)
    half_fov = math.atan(SENSOR / 2 / LENS)
    side_dist = max(size.y, size.z) * MARGIN / 2 / math.tan(half_fov) + size.x / 2
    profile = add_camera(scene, "HeadProfile", Vector((centre.x + side_dist, centre.y, centre.z)), centre.copy())

    os.makedirs(out_dir, exist_ok=True)
    for view, cam in (("front", front), ("profile", profile)):
        path = os.path.join(out_dir, core.head_shot_name(sku, view))
        render(scene, cam, path)
        if not os.path.isfile(path):
            print("HEADERROR: Blender rendered no %s image." % view)
            return 1
        print("HEADSHOT:%s:%s" % (view, path))
    return 0


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    try:
        code = main(*args)
    except Exception as e:  # report every failure on the HEADERROR line the add-on reads
        print("HEADERROR: %s: %s" % (type(e).__name__, e))
        code = 1
    sys.stdout.flush()
    sys.exit(code)

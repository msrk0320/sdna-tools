"""Pack Delivery sidebar panel (SuperDNA tab)."""

import os
from datetime import datetime

import bpy
from bpy.props import BoolProperty, CollectionProperty, IntProperty, PointerProperty, StringProperty

from . import blend_util, core

SLOTS = (("GLB", "glb"), ("SPP", "spp"), ("Textures folder", "textures"), ("Overlay", "overlays"))
STATE = {}        # plan, key, task_dir
CANDIDATES = {}   # slot name -> ranked [core.Candidate]


def _open_folder(path):
    os.startfile(path)  # Explorer's exit code is unreliable, so nothing is checked


def _abs(path):
    return os.path.normpath(bpy.path.abspath(path)) if path else ""


def _dirty():
    # Blender reports every file as dirty in --background mode, where nobody edits anything.
    return bpy.data.is_dirty and not bpy.app.background


def _key(context):
    s = context.window_manager.sdna_pack
    return (s.sku, s.task_id, s.glb, s.spp, s.textures, s.use_packed, tuple(o.path for o in s.overlays),
            bpy.data.filepath, _dirty())


def _inputs(context):
    s = context.window_manager.sdna_pack
    sku = s.sku.strip()
    mat = blend_util.find_material(sku)
    return core.Inputs(
        sku=sku, task_id=s.task_id.strip(), blend_path=bpy.data.filepath, blend_dirty=_dirty(),
        material_names=blend_util.materials_in_use(),
        image_dirs=blend_util.sku_image_dirs(mat, sku) if mat else [],
        glb=_abs(s.glb), spp=_abs(s.spp), textures=_abs(s.textures),
        overlays=[_abs(o.path) for o in s.overlays if o.path],
        dest_root=os.path.join(os.path.dirname(bpy.data.filepath), core.DELIVERY_DIR), candidates=CANDIDATES,
        missing_images=blend_util.missing_images(mat, sku) if mat else [],
        use_packed=s.use_packed, packed_maps=blend_util.packed_map_suffixes(mat, sku) if mat else [])


def _add_overlay(s, path):
    """Append path to the overlay list unless it is already there."""
    if path and _norm(path) not in {_norm(o.path) for o in s.overlays}:
        s.overlays.add().path = path


def _norm(path):
    return os.path.normcase(_abs(path))


def _refresh_textures(s):
    task_dir = STATE.get("task_dir")
    if not task_dir:
        return
    s.use_packed = False  # a new guess asks about packed maps again
    CANDIDATES["Textures folder"] = core.find_textures(task_dir, s.sku.strip(), _abs(s.spp) or None)
    cands = CANDIDATES["Textures folder"]
    s.textures = cands[0].path if cands else ""


def _on_spp_or_sku(self, context):
    _refresh_textures(self)  # the Textures guess depends on both


def _on_textures(self, context):
    if self.textures:
        self.use_packed = False  # a picked folder replaces the packed maps


def _glb_target():
    return os.path.splitext(bpy.data.filepath)[0] + ".glb"


def _report_failure(task_dir, plan, now, error):
    """Write the failure report; never let a report problem hide the real error."""
    try:
        report = core.write_report(task_dir, plan, now, "FAILED: %s" % error, blend_util.LAST_LOG)
    except OSError as e:
        return "%s (the report could not be written: %s)" % (error, e)
    return "%s (report: %s)" % (error, report)


class SDNAPACK_OverlayPath(bpy.types.PropertyGroup):
    path: StringProperty(name="Overlay", subtype="FILE_PATH")


class SDNAPACK_Settings(bpy.types.PropertyGroup):
    sku: StringProperty(name="SKU", description="Product SKU; delivered files are named after it",
                        update=_on_spp_or_sku)
    task_id: StringProperty(name="Task ID", description="Task ID (SDNA-...); working files are named after it")
    glb: StringProperty(name="GLB", subtype="FILE_PATH")
    spp: StringProperty(name="SPP", subtype="FILE_PATH", update=_on_spp_or_sku)
    textures: StringProperty(name="Textures folder", subtype="DIR_PATH", update=_on_textures)
    use_packed: BoolProperty(name="Use Packed Maps",
                             description="No Textures folder: deliver the maps already packed in the .blend")
    overlays: CollectionProperty(type=SDNAPACK_OverlayPath)


class SDNAPACK_OT_detect(bpy.types.Operator):
    bl_idname = "sdna_pack.detect"
    bl_label = "Detect"
    bl_description = "Fill SKU, task ID and every slot with the best guess from the task folder"

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the .blend first.")
            return {"CANCELLED"}
        s = context.window_manager.sdna_pack
        task_dir = os.path.dirname(bpy.data.filepath)
        STATE.clear()
        STATE["task_dir"] = task_dir
        s.task_id = core.task_id_from_blend(bpy.data.filepath)
        mats = blend_util.materials_in_use()
        if len(mats) == 1:
            s.sku = core.sku_from_material(mats[0])
        CANDIDATES.clear()
        CANDIDATES["GLB"] = core.find_glb(task_dir, s.task_id, s.sku.strip())  # never the earlier delivery
        CANDIDATES["SPP"] = core.find_spp(task_dir, s.task_id, s.sku.strip())
        CANDIDATES["Overlay"] = core.find_overlay(task_dir)
        s.overlays.clear()
        for c in CANDIDATES["Overlay"]:  # modellers sometimes send several; Preview lists each one
            _add_overlay(s, c.path)
        for slot, prop in (("GLB", "glb"), ("SPP", "spp")):
            setattr(s, prop, CANDIDATES[slot][0].path if CANDIDATES[slot] else "")
        _refresh_textures(s)
        self.report({"INFO"}, "Detected slots for %s / %s" % (s.sku or "?", s.task_id))
        return {"FINISHED"}


class SDNAPACK_OT_pick(bpy.types.Operator):
    bl_idname = "sdna_pack.pick"
    bl_label = "Use This Candidate"
    bl_options = {"INTERNAL"}

    prop: StringProperty()
    path: StringProperty()

    def execute(self, context):
        s = context.window_manager.sdna_pack
        if self.prop == "overlays":
            _add_overlay(s, self.path)
        else:
            setattr(s, self.prop, self.path)  # spp re-guesses Textures
        return {"FINISHED"}


class SDNAPACK_OT_add_overlays(bpy.types.Operator):
    bl_idname = "sdna_pack.add_overlays"
    bl_label = "Add Overlays"
    bl_description = "Pick one or more overlay images (Shift- or Ctrl-click to pick several)"
    bl_options = {"INTERNAL"}

    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN", "SKIP_SAVE"})
    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN", "SKIP_SAVE"})
    filter_image: BoolProperty(default=True, options={"HIDDEN", "SKIP_SAVE"})
    filter_folder: BoolProperty(default=True, options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        if bpy.data.filepath:
            self.directory = os.path.dirname(bpy.data.filepath) + os.sep
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        s = context.window_manager.sdna_pack
        for f in self.files:
            if f.name:
                _add_overlay(s, os.path.join(self.directory, f.name))
        return {"FINISHED"}


class SDNAPACK_OT_remove_overlay(bpy.types.Operator):
    bl_idname = "sdna_pack.remove_overlay"
    bl_label = "Remove Overlay"
    bl_description = "Take this overlay out of the delivery (the file is not touched)"
    bl_options = {"INTERNAL"}

    index: IntProperty()

    def execute(self, context):
        context.window_manager.sdna_pack.overlays.remove(self.index)
        return {"FINISHED"}


class SDNAPACK_OT_use_packed(bpy.types.Operator):
    bl_idname = "sdna_pack.use_packed"
    bl_label = "Yes, Use Them"
    bl_description = "These packed maps are the right ones: deliver them as they are, without a Textures folder"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        context.window_manager.sdna_pack.use_packed = True
        return {"FINISHED"}


class SDNAPACK_OT_pick_textures(bpy.types.Operator):
    bl_idname = "sdna_pack.pick_textures"
    bl_label = "No, Pick the Folder"
    bl_description = "Pick the Textures folder that holds the Mat_<SKU>_<Map>.png files"
    bl_options = {"INTERNAL"}

    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN", "SKIP_SAVE"})
    filter_folder: BoolProperty(default=True, options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        if bpy.data.filepath:
            self.directory = os.path.dirname(bpy.data.filepath) + os.sep
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        s = context.window_manager.sdna_pack
        s.use_packed = False
        s.textures = os.path.normpath(self.directory)
        return {"FINISHED"}


class SDNAPACK_OT_export_glb(bpy.types.Operator):
    bl_idname = "sdna_pack.export_glb"
    bl_label = "Export GLB"
    bl_description = "Export the open .blend to <name>.glb next to it (Client Validator settings) and use it"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return bool(bpy.data.filepath)

    def invoke(self, context, event):
        path = _glb_target()
        if os.path.exists(path):
            return context.window_manager.invoke_confirm(
                self, event, title="Overwrite GLB?", message="%s already exists." % os.path.basename(path),
                confirm_text="Overwrite")
        return self.execute(context)

    def execute(self, context):
        path = _glb_target()
        # Same call as the Client Validator's Export GLB.
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_image_format="AUTO",
                                  export_jpeg_quality=100)
        context.window_manager.sdna_pack.glb = path
        self.report({"INFO"}, "Exported %s" % path)
        return {"FINISHED"}


class SDNAPACK_OT_preview(bpy.types.Operator):
    bl_idname = "sdna_pack.preview"
    bl_label = "Preview"
    bl_description = "Check everything and list what would be delivered; writes nothing"

    def execute(self, context):
        plan = core.build_plan(_inputs(context))
        STATE["plan"], STATE["key"] = plan, _key(context)
        level = {"ERROR"} if plan.errors else ({"WARNING"} if plan.warnings else {"INFO"})
        self.report(level, "Preview: %d error(s), %d warning(s)" % (len(plan.errors), len(plan.warnings)))
        return {"FINISHED"}


class SDNAPACK_OT_run(bpy.types.Operator):
    bl_idname = "sdna_pack.run"
    bl_label = "Pack"
    bl_description = ("Write the next FinalDelivery\\<SKU>_v<N> next to the .blend; earlier versions are kept. "
                      "Needs a fresh, error-free Preview")

    @classmethod
    def poll(cls, context):
        plan = STATE.get("plan")
        return plan is not None and not plan.errors and STATE.get("key") == _key(context)

    def execute(self, context):
        plan = core.build_plan(_inputs(context))      # re-run every check
        task_dir = os.path.dirname(bpy.data.filepath)
        if plan.errors:
            STATE["plan"] = plan
            self.report({"ERROR"}, plan.errors[0])
            return {"CANCELLED"}
        if plan.warnings != STATE["plan"].warnings:
            STATE["plan"] = plan                      # shown in the panel; the next Pack goes ahead
            self.report({"WARNING"}, "Warnings changed since Preview; check them and press Pack again.")
            return {"CANCELLED"}
        expected = len(blend_util.wired_images(blend_util.find_material(plan.sku)))
        now = datetime.now()
        blend_util.LAST_LOG = ""                      # never report an earlier pack's Blender output
        try:
            result = core.execute(plan, lambda staging: blend_util.make_packed_blend(staging, plan.sku, expected,
                                                                                      packed=plan.packed), now=now)
        except core.PackError as e:
            self.report({"ERROR"}, _report_failure(task_dir, plan, now, e))
            return {"CANCELLED"}
        outcome = "OK" + (" (old delivery archived as %s)" % os.path.basename(result.archive)
                          if result.archive else "")
        STATE["plan"] = None
        _open_folder(result.dest)
        try:
            core.write_report(task_dir, plan, now, outcome, blend_util.LAST_LOG)
        except OSError as e:
            self.report({"WARNING"}, "Packed %s, but the report could not be written: %s" % (result.dest, e))
            return {"FINISHED"}
        self.report({"INFO"}, "Packed %s" % result.dest)
        return {"FINISHED"}


def _make_menu(slot, prop):
    def draw(self, context):
        cands = CANDIDATES.get(slot, [])
        if not cands:
            self.layout.label(text="Press Detect first")
        task_dir = STATE.get("task_dir", "")
        for c in cands:
            try:
                shown = os.path.relpath(c.path, task_dir)
            except ValueError:  # different drive
                shown = c.path
            op = self.layout.operator(SDNAPACK_OT_pick.bl_idname,
                                      text="%s  ·  %s  ·  tier %d" % (shown, core.fmt_time(c.mtime), c.tier))
            op.prop, op.path = prop, c.path

    name = "SDNAPACK_MT_" + prop
    return type(name, (bpy.types.Menu,), {"bl_idname": name, "bl_label": slot + " candidates", "draw": draw})


def _draw_overlays(layout, s):
    box = layout.box()
    row = box.row(align=True)
    row.label(text="Overlays (%d)" % len(s.overlays), icon="IMAGE_DATA")
    row.operator(SDNAPACK_OT_add_overlays.bl_idname, text="", icon="ADD")
    row.menu("SDNAPACK_MT_overlays", text="", icon="DOWNARROW_HLT")
    for i, item in enumerate(s.overlays):
        r = box.row(align=True)
        r.prop(item, "path", text="")
        r.operator(SDNAPACK_OT_remove_overlay.bl_idname, text="", icon="X").index = i


def _draw_packed_question(layout, s):
    packed = blend_util.packed_images(blend_util.find_material(s.sku.strip()))
    if not packed:
        return
    box = layout.box()
    box.label(text="No Textures folder found. The .blend has %d packed map(s):" % len(packed), icon="QUESTION")
    for img in packed:
        box.label(text="%s  (%d x %d)" % (img.name, img.size[0], img.size[1]), icon="IMAGE_DATA")
    box.label(text="Are these the right maps?")
    row = box.row(align=True)
    row.operator(SDNAPACK_OT_use_packed.bl_idname, icon="CHECKMARK")
    row.operator(SDNAPACK_OT_pick_textures.bl_idname, icon="FILEBROWSER")


MENUS = tuple(_make_menu(slot, prop) for slot, prop in SLOTS)


class SDNAPACK_PT_panel(bpy.types.Panel):
    bl_label = "Pack Delivery"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SuperDNA"

    def draw(self, context):
        s = context.window_manager.sdna_pack
        layout = self.layout
        col = layout.column(align=True)
        col.prop(s, "sku")
        col.prop(s, "task_id")
        layout.operator(SDNAPACK_OT_detect.bl_idname, icon="VIEWZOOM")
        for slot, prop in SLOTS:
            if prop == "overlays":
                _draw_overlays(layout, s)
                continue
            if prop == "textures" and s.use_packed:
                row = layout.row(align=True)
                row.label(text="Textures: packed maps in the .blend", icon="PACKAGE")
                row.operator(SDNAPACK_OT_pick_textures.bl_idname, text="", icon="FILEBROWSER")
                continue
            row = layout.row(align=True)
            row.prop(s, prop, text=slot)
            row.menu("SDNAPACK_MT_" + prop, text="", icon="DOWNARROW_HLT")
            if prop == "glb" and not s.glb and bpy.data.filepath:
                box = layout.box()
                box.label(text="No GLB found. Export it first.", icon="ERROR")
                box.operator(SDNAPACK_OT_export_glb.bl_idname, icon="EXPORT")
            elif prop == "textures" and not s.textures:
                _draw_packed_question(layout, s)
        row = layout.row(align=True)
        row.operator(SDNAPACK_OT_preview.bl_idname, icon="HIDE_OFF")
        row.operator(SDNAPACK_OT_run.bl_idname, icon="PACKAGE")
        plan = STATE.get("plan")
        if plan:
            box = layout.box()
            box.label(text="→ %s\\%s" % (core.DELIVERY_DIR, os.path.basename(plan.dest)), icon="FILE_FOLDER")
            for e in plan.errors:
                box.label(text=e, icon="CANCEL")
            for w in plan.warnings:
                box.label(text=w, icon="ERROR")
            for src, rel in plan.copies:
                box.label(text="%s → %s" % (os.path.basename(src), rel))
            box.label(text="open .blend (packed copy) → %s.blend" % plan.sku)
            if plan.maps:
                box.label(text="%d texture map(s) → packed inside %s.blend" % (len(plan.maps), plan.sku))
            elif plan.packed:
                box.label(text="packed maps → kept inside %s.blend" % plan.sku)


CLASSES = (SDNAPACK_OverlayPath, SDNAPACK_Settings, SDNAPACK_OT_detect, SDNAPACK_OT_pick, SDNAPACK_OT_add_overlays,
           SDNAPACK_OT_remove_overlay, SDNAPACK_OT_use_packed, SDNAPACK_OT_pick_textures, SDNAPACK_OT_export_glb,
           SDNAPACK_OT_preview,
           SDNAPACK_OT_run, *MENUS, SDNAPACK_PT_panel)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.WindowManager.sdna_pack = PointerProperty(type=SDNAPACK_Settings)


def unregister():
    del bpy.types.WindowManager.sdna_pack
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
    STATE.clear()
    CANDIDATES.clear()

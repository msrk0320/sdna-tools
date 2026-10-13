"""Pack Delivery core: plans and executes a SuperDNA eyewear delivery.

Plain Python only. Never import bpy here; unit tests run without Blender.
"""

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime

# The Painter export map suffixes and the names they are delivered under.
MAP_SUFFIXES = ("BaseColor", "Roughness", "Metallic", "Normal", "Transmissive")
DELIVERED_NAMES = {"BaseColor": "basecolor", "Roughness": "roughness", "Metallic": "metalness",
                   "Normal": "normal", "Transmissive": "transmissive"}
REQUIRED_MAPS = ("BaseColor", "Roughness")
OPTIONAL_MAPS = ("Metallic", "Normal", "Transmissive")
RESERVED_NAMES = ({"CON", "PRN", "AUX", "NUL"}
                  | {"COM%d" % i for i in range(1, 10)}
                  | {"LPT%d" % i for i in range(1, 10)})
INVALID_CHARS = set('\\/:*?"<>|')
MAX_PATH_LEN = 240
DEFAULT_DEST_ROOT = r"D:\SuperDNA\FinalDelivery"
DELIVERY_DIR = "FinalDelivery"  # next to the .blend; every pack adds <SKU>_v<N> inside it
OVERLAY_DELIVERED = "Overlay"
PACK_DIR = "Texture"  # maps staged for packing into the .blend, removed before the delivery is published
QA_RE = re.compile(r"_QA_v(\d+)$", re.IGNORECASE)
# Trailing version words people add to working files, also stacked: _v2, _r1, _rev3, _ver4, _final, _fix
NAME_SUFFIX_RE = re.compile(r"(?:[_ ](?:v|r|rev|ver)\d+|[_ ](?:final|fix|fixed))+$", re.IGNORECASE)


class PackError(Exception):
    """A failure during packing; the message is shown to the artist."""


def sku_from_material(name):
    """'MAT_ABC123 45.001' -> 'ABC123 45'."""
    stem = re.sub(r"\.\d{3}$", "", name.strip())
    return re.sub(r"(?i)^mat_", "", stem)


def name_base(stem):
    """Drop trailing version words: 'SDNA-000001_ABC123_v2_final' -> 'SDNA-000001_ABC123'."""
    return NAME_SUFFIX_RE.sub("", stem)


def name_version(stem):
    """N of the last _vN/_rN/_revN/_verN suffix; 0 without one."""
    m = NAME_SUFFIX_RE.search(stem)
    numbers = re.findall(r"\d+", m.group(0)) if m else []
    return int(numbers[-1]) if numbers else 0


def is_task_name(stem, task_id, sku=""):
    """True for <task>, <task>_<SKU> or <SKU>, each optionally followed by version words."""
    if not task_id:
        return False
    names = {task_id}
    if sku:
        names |= {sku, "%s_%s" % (task_id, sku), "%s %s" % (task_id, sku)}
    return name_base(stem).lower() in {n.lower() for n in names}


def task_id_from_blend(blend_path):
    """'SDNA-000001_shader.blend' and 'SDNA-000001_ABC123_v2.blend' -> 'SDNA-000001';
    any other name -> its stem without version words ('ABC123_r1.blend' -> 'ABC123')."""
    base = name_base(os.path.splitext(os.path.basename(blend_path))[0])
    m = re.match(r"^(SDNA-\d+)(?:[_ ].*)?$", base, re.IGNORECASE)
    return m.group(1) if m else base


def sku_problems(sku, dest_root=DEFAULT_DEST_ROOT):
    if not sku:
        return ["SKU is empty."]
    problems = []
    bad = sorted(set(sku) & INVALID_CHARS)
    if bad:
        problems.append("SKU contains characters Windows does not allow: %s" % " ".join(bad))
    if sku.endswith((" ", ".")):
        problems.append("SKU must not end with a space or a dot.")
    if sku.upper() in RESERVED_NAMES:
        problems.append("SKU %r is a reserved Windows name." % sku)
    longest = os.path.join(dest_root, sku + "_v999.__packing", PACK_DIR, "%s_transmissive.png" % sku)
    if len(longest) > MAX_PATH_LEN:
        problems.append("Delivery path would be longer than %d characters: %s" % (MAX_PATH_LEN, longest))
    return problems


def fmt_time(mtime):
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- discovery

@dataclass
class Candidate:
    path: str
    tier: int
    mtime: float
    version: int = 0  # QA version number; the highest ranks first within a tier


def rank(cands):
    return sorted(cands, key=lambda c: (c.tier, -c.version, -c.mtime, c.path.lower()))


def _is_backup(name):
    return "backup" in name.lower() or name.lower() == "claude_experiments"  # Claude's scratch: never delivered


def is_delivery_dir(name, sku):
    """FinalDelivery, plus <SKU>, <SKU>_old_<time> and <SKU>.__packing that add-on 1.1.0 wrote next to the .blend."""
    n, s = name.lower(), sku.lower()
    if n == DELIVERY_DIR.lower():
        return True
    return bool(s) and (n == s or n.startswith(s + "_old_") or n == s + ".__packing")


def _walk(root, sku=""):
    """os.walk that never enters backup folders, claude_experiments or this SKU's deliveries."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _is_backup(d) and not is_delivery_dir(d, sku)]
        yield dirpath, dirnames, filenames


def _files(root, ext, sku=""):
    for dirpath, _dirs, filenames in _walk(root, sku):
        for f in filenames:
            if f.lower().endswith(ext):
                yield os.path.join(dirpath, f)


def texture_pattern(sku):
    return re.compile(r"^Mat_%s_(%s)\.png$" % (re.escape(sku), "|".join(MAP_SUFFIXES)), re.IGNORECASE)


def qa_version(path):
    """N of a '<name>_QA_vN' file, or of the '<name>_QA_vN' folder it sits in; None otherwise."""
    for name in (_stem(path), os.path.basename(os.path.dirname(path))):
        m = QA_RE.search(name)
        if m:
            return int(m.group(1))
    return None


def find_glb(task_dir, task_id, sku=""):
    paths = list(_files(task_dir, ".glb", sku))
    parent = os.path.dirname(os.path.normpath(task_dir))
    for f in os.listdir(parent):
        p = os.path.join(parent, f)
        if f.lower().endswith(".glb") and os.path.isfile(p):
            paths.append(p)
    out = []
    for p in paths:
        name = os.path.basename(p).lower()
        version = qa_version(p)
        if "_volume" in name:
            tier = 4
        elif version is not None:
            tier = 1
        elif is_task_name(_stem(p), task_id, sku):
            tier, version = 2, name_version(_stem(p))  # the highest _vN/_rN ranks first
        else:
            tier = 3
        out.append(Candidate(p, tier, os.path.getmtime(p), version or 0))
    return rank(out)


def find_spp(task_dir, task_id, sku=""):
    out = []
    for p in _files(task_dir, ".spp", sku):
        name = os.path.basename(p).lower()
        if "_autosave" in name:
            continue
        version = qa_version(p)
        if version is not None:
            tier = 1
        elif is_task_name(_stem(p), task_id, sku):
            tier, version = 2, name_version(_stem(p))  # the highest _vN/_rN ranks first
        else:
            tier = 3
        out.append(Candidate(p, tier, os.path.getmtime(p), version or 0))
    return rank(out)


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0].lower()


def find_textures(task_dir, sku, chosen_spp):
    """Only '<spp stem>\\Textures' folders (Painter export layout) holding Mat_<SKU>_BaseColor.png."""
    spp_stems = {_stem(p) for p in _files(task_dir, ".spp")}
    chosen = _stem(chosen_spp) if chosen_spp else None
    pattern = texture_pattern(sku)
    out = []
    for dirpath, _dirs, filenames in _walk(task_dir):
        if os.path.basename(dirpath).lower() != "textures":
            continue
        parent = os.path.basename(os.path.dirname(dirpath)).lower()
        if parent not in spp_stems:
            continue
        base = next((f for f in filenames
                     if (m := pattern.match(f)) and m.group(1).lower() == "basecolor"), None)
        if not base:
            continue
        tier = 1 if parent == chosen else 2
        out.append(Candidate(dirpath, tier, os.path.getmtime(os.path.join(dirpath, base))))
    return rank(out)


def find_overlay(task_dir):
    out = []
    for f in os.listdir(task_dir):
        p = os.path.join(task_dir, f)
        if os.path.isfile(p) and "overlay" in f.lower() and f.lower().endswith(".png"):
            out.append(Candidate(p, 1, os.path.getmtime(p)))
    return rank(out)


def overlay_names(paths):
    """One overlay is delivered as Overlay.<ext>; several as Overlay_01.<ext>, Overlay_02.<ext>, ... in order."""
    def ext(p):
        return os.path.splitext(p)[1].lower()
    if len(paths) == 1:
        return [OVERLAY_DELIVERED + ext(paths[0])]
    return ["%s_%02d%s" % (OVERLAY_DELIVERED, i, ext(p)) for i, p in enumerate(paths, 1)]


def next_version(dest_root, sku):
    """1 + the highest <SKU>_v<N> folder already in dest_root; 1 when there is none."""
    pattern = re.compile(r"^%s_v(\d+)$" % re.escape(sku), re.IGNORECASE)
    try:
        names = os.listdir(dest_root)
    except OSError:  # FinalDelivery is created by the first pack
        names = []
    return 1 + max((int(m.group(1)) for n in names if (m := pattern.match(n))), default=0)


# ---------------------------------------------------------------- textures

def scan_textures(folder, sku):
    pattern = texture_pattern(sku)
    canonical = {s.lower(): s for s in MAP_SUFFIXES}
    maps, skipped = {}, []
    for f in sorted(os.listdir(folder)):
        p = os.path.join(folder, f)
        if not os.path.isfile(p):
            continue
        m = pattern.match(f)
        if m:
            maps[canonical[m.group(1).lower()]] = p
        else:
            skipped.append(f)
    return maps, skipped


def png_bit_depth(path):
    """Bit depth from the IHDR chunk (always first, depth at byte 24), or None if not a PNG."""
    try:
        with open(path, "rb") as f:
            head = f.read(25)
    except OSError:
        return None
    if len(head) < 25 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return head[24]


# ---------------------------------------------------------------- plan

@dataclass
class Inputs:
    sku: str
    task_id: str
    blend_path: str
    blend_dirty: bool
    material_names: list
    image_dirs: list          # folders of wired Mat_<SKU>_<Map> images in the open .blend
    glb: str
    spp: str
    textures: str
    overlays: list            # overlay images, in the order picked
    dest_root: str = DEFAULT_DEST_ROOT
    candidates: dict = field(default_factory=dict)   # slot name -> ranked [Candidate]
    missing_images: list = field(default_factory=list)  # wired non-SKU images whose file is gone (not packed)


@dataclass
class PackPlan:
    sku: str
    dest: str
    staging: str
    copies: list = field(default_factory=list)     # (src_abs, dst_rel)
    maps: list = field(default_factory=list)       # (src_abs, dst_rel): packed into the .blend, not delivered
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


def _norm(path):
    return os.path.normcase(os.path.normpath(path))


def _slot_warnings(slot, chosen, cands, mtime_of):
    """Older-than-newest and top-tier tie warnings for one slot."""
    if not chosen or not cands:
        return []
    out = []
    match = next((c for c in cands if _norm(c.path) == _norm(chosen)), None)
    chosen_mtime = match.mtime if match else mtime_of(chosen)
    # A newer _volume.glb (tier 4) is a by-product of every export, not a sign the chosen file is stale.
    pool = [c for c in cands if c.tier < 4] or cands
    newest = max(pool, key=lambda c: c.mtime)
    if chosen_mtime < newest.mtime:
        out.append("%s: the chosen file is older than the newest candidate %s (%s)"
                   % (slot, newest.path, fmt_time(newest.mtime)))
    ties = [c for c in cands if (c.tier, c.version) == (cands[0].tier, cands[0].version)]
    if len(ties) > 1:
        others = [c for c in ties if _norm(c.path) != _norm(chosen)]
        out.append("%s: %d candidates tie for best guess; also: %s"
                   % (slot, len(ties), ", ".join("%s (%s)" % (c.path, fmt_time(c.mtime)) for c in others)))
    return out


def build_plan(inp):
    sku, task = inp.sku.strip(), inp.task_id.strip()
    dest = os.path.join(inp.dest_root, "%s_v%d" % (sku, next_version(inp.dest_root, sku)))
    plan = PackPlan(sku=sku, dest=dest, staging=dest + ".__packing")
    err, warn = plan.errors, plan.warnings

    # names and the open file
    if not task:
        err.append("Task ID is empty.")
    err.extend(sku_problems(sku, inp.dest_root))
    if not inp.blend_path:
        err.append("Save the .blend first.")
    elif task and not is_task_name(_stem(inp.blend_path), task, sku):
        err.append("Open the final %s.blend (or rename it) before packing; the SKU and _v1, _r1, _final "
                   "are allowed in the name." % task)
    if inp.blend_dirty:
        err.append("Save the .blend first: it has unsaved changes.")
    mats = list(dict.fromkeys(inp.material_names))
    if len(mats) != 1:
        err.append("The .blend must use exactly one material on mesh objects; found %d: %s"
                   % (len(mats), ", ".join(mats) or "none"))
    elif sku and sku_from_material(mats[0]) != sku:
        err.append("Material %s does not match SKU %s (expected Mat_%s)." % (mats[0], sku, sku))
    for path in inp.missing_images:
        err.append("Image file missing: %s (the material uses it, so it cannot be packed)" % path)

    # slots
    slots = [("GLB", inp.glb, os.path.isfile), ("SPP", inp.spp, os.path.isfile),
             ("Textures folder", inp.textures, os.path.isdir)]
    present = {}
    for slot, path, exists in slots:
        if not path:
            err.append("%s slot is empty." % slot)
        elif not exists(path):
            err.append("%s not found: %s" % (slot, path))
        else:
            present[slot] = path

    overlays = []
    if not inp.overlays:
        err.append("Overlay slot is empty.")
    for path in dict.fromkeys(inp.overlays):
        if os.path.isfile(path):
            overlays.append(path)
        else:
            err.append("Overlay not found: %s" % path)

    # copies (only for slots that exist)
    if "GLB" in present:
        plan.copies.append((present["GLB"], sku + ".glb"))
    if "SPP" in present:
        plan.copies.append((present["SPP"], sku + ".spp"))
    plan.copies += list(zip(overlays, overlay_names(overlays)))

    maps = {}
    if "Textures folder" in present:
        maps, plan.skipped = scan_textures(present["Textures folder"], sku)
        for suffix in REQUIRED_MAPS:
            if suffix not in maps:
                err.append("Texture folder has no Mat_%s_%s.png" % (sku, suffix))
        for suffix in OPTIONAL_MAPS:
            if suffix not in maps:
                warn.append("No %s map (fine if the product does not use it)." % DELIVERED_NAMES[suffix])
        for suffix in MAP_SUFFIXES:
            if suffix in maps:
                plan.maps.append((maps[suffix], os.path.join(PACK_DIR, "%s_%s.png" % (sku, DELIVERED_NAMES[suffix]))))
        deep = [os.path.basename(p) for p in maps.values() if png_bit_depth(p) == 16]
        if deep:
            warn.append("16-bit textures (guideline says 8-bit; waiting on lead): %s" % ", ".join(sorted(deep)))
        other_dirs = sorted({d for d in inp.image_dirs if _norm(d) != _norm(present["Textures folder"])})
        if other_dirs:
            warn.append("The .blend uses SKU textures from %s; the delivered .blend will be relinked to the "
                        "selected Textures folder." % ", ".join(other_dirs))

    # warnings
    for slot in ("GLB", "SPP"):
        if slot in present and task and task.lower() not in os.path.basename(present[slot]).lower():
            warn.append("%s name does not contain the task ID %s: %s" % (slot, task, os.path.basename(present[slot])))

    def tex_mtime(folder):
        base = maps.get("BaseColor")
        return os.path.getmtime(base) if base else os.path.getmtime(folder)

    for slot, mtime_of in (("GLB", os.path.getmtime), ("SPP", os.path.getmtime),
                           ("Textures folder", tex_mtime)):
        if slot in present:
            warn.extend(_slot_warnings(slot, present[slot], inp.candidates.get(slot, []), mtime_of))
    if len(overlays) == 1:  # with several picked, every candidate may be meant
        warn.extend(_slot_warnings("Overlay", overlays[0], inp.candidates.get("Overlay", []), os.path.getmtime))

    if " " in sku:
        warn.append("SKU contains spaces; every delivered file will contain them too.")
    for path in overlays:
        if "GLB" in present and os.path.getmtime(path) < os.path.getmtime(present["GLB"]):
            warn.append("Overlay is older than the chosen GLB; it may be stale: %s" % os.path.basename(path))
    return plan


# ---------------------------------------------------------------- execute

@dataclass
class ExecResult:
    dest: str
    archive: str = None


def archive_path(dest, now):
    base = "%s_old_%s" % (dest, now.strftime("%Y%m%d-%H%M%S"))
    path, n = base, 2
    while os.path.exists(path):
        path = "%s_%d" % (base, n)
        n += 1
    return path


def rename_with_retry(src, dst, folder, tries=3, delay=1.0, sleep=time.sleep):
    """folder: the delivery folder to name in the 'close it in Explorer' message."""
    for attempt in range(tries):
        try:
            os.rename(src, dst)
            return
        except OSError:  # PermissionError on Windows when Explorer holds the folder
            if attempt == tries - 1:
                raise PackError("Could not rename %s. Close the %s folder in Explorer (and any program "
                                "using its files) and press Pack again." % (src, folder))
            sleep(delay)


def _verify(plan, staging):
    """Staging must contain exactly the planned files plus <SKU>.blend, none of them empty."""
    expected = [rel for _src, rel in plan.copies] + [plan.sku + ".blend"]
    for rel in expected:
        p = os.path.join(staging, rel)
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            raise PackError("Missing or empty in staging: %s" % rel)
    wanted = {os.path.normcase(rel) for rel in expected}
    extra = sorted(os.path.relpath(os.path.join(d, f), staging) for d, _s, fs in os.walk(staging) for f in fs
                   if os.path.normcase(os.path.relpath(os.path.join(d, f), staging)) not in wanted)
    if extra:
        raise PackError("Unexpected files in staging: %s" % ", ".join(extra))


def execute(plan, make_blend, now=None, sleep=time.sleep):
    if plan.errors:
        raise PackError("The plan has errors; press Preview and fix them first.")
    now = now or datetime.now()
    staging, dest = plan.staging, plan.dest
    archive = None
    try:
        if os.path.exists(staging):
            shutil.rmtree(staging)
        os.makedirs(os.path.join(staging, PACK_DIR))
        for src, rel in plan.copies + plan.maps:
            os.makedirs(os.path.dirname(os.path.join(staging, rel)), exist_ok=True)
            shutil.copy2(src, os.path.join(staging, rel))
        make_blend(staging)
        shutil.rmtree(os.path.join(staging, PACK_DIR))  # the maps are inside the .blend now
        _verify(plan, staging)
        if os.path.exists(dest):
            archive = archive_path(dest, now)
            rename_with_retry(dest, archive, sleep=sleep, folder=dest)
        rename_with_retry(staging, dest, sleep=sleep, folder=dest)
    except Exception as e:
        shutil.rmtree(staging, ignore_errors=True)
        if archive and os.path.exists(archive) and not os.path.exists(dest):
            try:
                os.rename(archive, dest)  # put the old delivery back
            except OSError as undo:
                raise PackError("%s; ALSO could not restore the old delivery from %s: %s"
                                % (e, archive, undo)) from e
        if isinstance(e, PackError):
            raise
        raise PackError("%s: %s" % (type(e).__name__, e)) from e
    return ExecResult(dest=dest, archive=archive)


def check_packed(stdout, returncode, expected):
    if returncode != 0:
        raise PackError("Background Blender failed (exit code %s)." % returncode)
    problems = re.findall(r"^PACKERROR: (.*)$", stdout or "", re.MULTILINE)
    if problems:
        raise PackError("Packing problem: %s" % "; ".join(p.strip() for p in problems))
    m = re.search(r"^PACKED:(\d+)/(\d+)\s*$", stdout or "", re.MULTILINE)
    if not m:
        raise PackError("Background Blender did not report packed images.")
    n, w = int(m.group(1)), int(m.group(2))
    if n != w:
        raise PackError("Only %d of %d images could be packed." % (n, w))
    if w != expected:
        raise PackError("Packed %d images but the open .blend uses %d." % (w, expected))
    return n


def write_report(task_dir, plan, now, outcome, log=""):
    lines = ["Pack Delivery report",
             "Time: %s" % now.strftime("%Y-%m-%d %H:%M:%S"),
             "SKU: %s" % plan.sku,
             "Destination: %s" % plan.dest,
             "Outcome: %s" % outcome,
             "", "Copies:"]
    lines += ["  %s -> %s" % (src, rel) for src, rel in plan.copies]
    lines += ["  (packed copy of the open .blend) -> %s.blend" % plan.sku]
    lines += ["  %s -> packed into %s.blend" % (src, plan.sku) for src, _rel in plan.maps]
    lines += ["", "Errors:"]
    lines += ["  " + e for e in plan.errors] or ["  none"]
    lines += ["", "Warnings:"] + (["  " + w for w in plan.warnings] or ["  none"])
    lines += ["", "Skipped files in the Textures folder:"] + (["  " + s for s in plan.skipped] or ["  none"])
    lines += ["", "Background Blender output:", log or "  (none)"]
    path = os.path.join(task_dir, "pack_report_%s.txt" % now.strftime("%Y%m%d-%H%M%S"))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path

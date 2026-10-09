# PyInstaller spec for SppDowngrader.exe - GUI wrapper for uspp_tool
# Build: pyinstaller SppDowngrader.spec --noconfirm
# Output: dist/SppDowngrader.exe (one file)
#
# Bundles all data into a single "profiles/" dir inside the exe; uspp_tool sets
# SPP_PROFILE_DIR to it at startup, and the frozen-aware loaders read from there.

import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

SPECPATH_DIR = os.path.dirname(os.path.abspath(SPEC))
ROOT = os.path.join(SPECPATH_DIR, "universal-spp", "spp_downgrader")
PROFILES = os.path.join(ROOT, "profiles")
LIB = os.path.join(ROOT, "spp_extractor", "lib")

# All json data flattened into the bundle's profiles/ dir
datas = [
    (os.path.join(PROFILES, "*.json"), "profiles"),
    (os.path.join(PROFILES, "decisions", "*.json"), "profiles/decisions"),
    (os.path.join(LIB, "v10_schema.json"), "profiles"),
    (os.path.join(LIB, "v10_baking_schema.json"), "profiles"),
    (os.path.join(ROOT, "lossiness_messages.json"), "profiles"),
]

# Auto-generated per-version schemas/defaults
for fn in os.listdir(LIB):
    if fn.endswith(("_schema.json", "_defaults.json")):
        datas.append((os.path.join(LIB, fn), "profiles"))

# tkinterdnd2 data
datas += collect_data_files("tkinterdnd2")

# h5py's HDF5 runtime DLLs
binaries = collect_dynamic_libs("h5py")

a = Analysis(
    [os.path.join(SPECPATH_DIR, "gui.py")],
    pathex=[ROOT, os.path.join(ROOT, "spp_extractor"), os.path.join(ROOT, "spp_builder")],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "h5py", "h5py.defs", "h5py.utils", "h5py._proxy", "h5py.h5ac",
        "numpy", "mmh3", "yaml", "lz4", "lz4.block", "lz4._version",
        "pyspng", "pyspng._pyspng_c",
        "lib.migration_profile", "lib.hbo_decode",
        "lib.lossiness", "lib.raster_manifest", "lib.config_manager", "lib.type_code_mapper",
        "lib.hbo_parser", "lib.dict_remover", "hbo_encoder", "spp_builder",
        "spp_extractor", "spp_ext_models", "spp_ext_decoder",
        "lib.hbo_reserializer", "lib.hbo_reserializer.runtime",
        "lib.hbo_reserializer.models", "lib.hbo_reserializer.serializer",
        "lib.hbo_reserializer._readers", "lib.hbo_reserializer._write_inline",
        "lib.hbo_reserializer._write_registry", "lib.hbo_reserializer._transforms",
        "lib.hbo_reserializer._schema", "lib.hbo_reserializer._helpers",
        "lib.hbo_reserializer._classify", "lib.hbo_reserializer._raster_plan",
        "lib.hbo_reserializer._raster_replace", "raster_resources",
        "uspp_tool", "tkinterdnd2",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["PySide2", "PySide6", "PyQt5"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SppDowngrader",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

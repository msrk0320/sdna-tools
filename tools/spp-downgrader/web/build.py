#!/usr/bin/env python3
"""Build script for the web version of SPP Downgrader."""

import os
import sys
import shutil
import zipfile
from pathlib import Path

def main():
    # Resolve paths relative to this script
    script_dir = Path(__file__).parent.absolute()
    repo_root = script_dir.parent.parent.parent  # Up to SDNA-Tools
    engine_src = repo_root / 'tools' / 'spp-downgrader' / 'universal-spp' / 'spp_downgrader'
    dist_dir = script_dir / 'dist'

    # Wipe and recreate dist
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True)

    # Copy static files
    static_files = ['index.html', 'app.js', 'worker.js', 'style.css']
    for fname in static_files:
        src = script_dir / fname
        dst = dist_dir / fname
        if src.exists():
            shutil.copy2(src, dst)
            print(f"Copied {fname}")
        else:
            print(f"Warning: {fname} not found", file=sys.stderr)

    # Create engine.zip
    zip_path = dist_dir / 'engine.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(engine_src):
            # Skip excluded dirs
            dirs[:] = [d for d in dirs if d not in ('__pycache__', 'debug')]

            for fname in files:
                # Skip excluded files
                if fname.endswith(('.pyc', '.md', '.spec')):
                    continue

                fpath = Path(root) / fname
                # Archive path: relative to engine_src
                arcname = fpath.relative_to(engine_src)
                zf.write(fpath, arcname)

    zip_size = zip_path.stat().st_size
    print(f"Created engine.zip ({zip_size} bytes)")

    print(f"\nBuild complete. Files in {dist_dir}")

if __name__ == '__main__':
    main()

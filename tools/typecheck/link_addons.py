"""Link Odoo addons and the MediLab modules into odoo/addons of the Odoo source, where pyright resolves them.

pyright finds odoo.addons.<name> only inside odoo/addons. A link shows the current code of a module, unlike a copy:
a symbolic link on Linux and macOS, a directory junction on Windows, which needs no administrator rights.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

MANIFEST = "__manifest__.py"


def is_link(path):
    return path.is_symlink() or path.is_junction()


def create_link(link, target):
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        if result.returncode:
            sys.exit(f"Could not link {link} to {target}: {result.stderr or result.stdout}")
    else:
        os.symlink(os.path.relpath(target, link.parent), link, target_is_directory=True)


def replace_link(link, target, copied):
    """Point link at target. A folder there is removed only when copied says an earlier copy of target left it."""
    if is_link(link):
        if link.exists() and link.samefile(target):
            return
        link.unlink()
    elif link.exists():
        if not copied:
            sys.exit(f"{link} is a folder, not a link. Move it away and run again.")
        shutil.rmtree(link)
    create_link(link, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="the Odoo source folder")
    parser.add_argument("modules", type=Path, help="the folder of the MediLab modules")
    parser.add_argument("addons", nargs="*", help="the Odoo addons in <source>/addons to link")
    args = parser.parse_args()
    addons_folder = args.source / "odoo" / "addons"
    if not addons_folder.is_dir():
        sys.exit(f"{addons_folder} not found. Run: task dev:odoo-source")
    targets = {name: (args.source / "addons" / name, True) for name in args.addons}
    targets |= {path.name: (path, False) for path in args.modules.iterdir() if (path / MANIFEST).is_file()}
    for name, (target, copied) in targets.items():
        if not target.is_dir():
            sys.exit(f"{target} not found. Run: task dev:odoo-source")
        replace_link(addons_folder / name, target.resolve(), copied)
    for path in addons_folder.iterdir():
        if is_link(path) and path.name not in targets:
            path.unlink()


if __name__ == "__main__":
    main()

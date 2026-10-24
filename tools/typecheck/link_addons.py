"""Link Odoo addons and the MediLab modules into odoo/addons of the Odoo source, where pyright resolves them.

pyright finds odoo.addons.<name> only inside odoo/addons. A link shows the current code of a module, unlike a copy:
a symbolic link on Linux and macOS, a directory junction on Windows, which needs no administrator rights.
The links this script made are recorded in medilab-links.json of the Odoo source. Only those are replaced or removed;
other links in odoo/addons are left alone, and a folder under a name it needs is replaced only after the user confirms.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MANIFEST = "__manifest__.py"
RECORD = "medilab-links.json"
WINDOWS = os.name == "nt"


class LinkError(Exception):
    pass


def is_link(path):
    return path.is_symlink() or path.is_junction()


def create_link(link, target):
    if WINDOWS:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise LinkError(f"Could not link {link} to {target}: {result.stderr or result.stdout}")
    else:
        os.symlink(os.path.relpath(target, link.parent), link, target_is_directory=True)


def remove_link(link):
    """Remove the link only, never what it points at."""
    if link.is_junction():
        # RemoveDirectoryW deletes a junction itself, whatever its target holds.
        os.rmdir(link)
    elif link.is_symlink():
        link.unlink()
    else:
        raise LinkError(f"{link} is not a link; refusing to remove it.")


def valid_name(name):
    return (
        isinstance(name, str)
        and name not in ("", ".", "..")
        and not name.endswith((".", " "))
        and not any(part in name for part in ("/", "\\", ":"))
    )


def ask_to_replace(folder):
    """Ask whether to delete folder and link its name instead. Without a terminal, the answer is no."""
    if not sys.stdin.isatty():
        return False
    answer = input(f"{folder} is a folder, not a link. Delete it and link the name instead? [y/N] ")
    return answer.strip().lower() in ("y", "yes")


class Links:
    """The links in an odoo/addons folder, and which of them this script made."""

    def __init__(self, folder, record, confirm=ask_to_replace):
        self.folder = folder
        self.record = record
        self.confirm = confirm
        try:
            self.made = json.loads(record.read_text(encoding="utf-8")) if record.exists() else {}
        except (OSError, ValueError) as error:
            raise LinkError(f"{record} cannot be read: {error}. Delete it and run again.") from error
        if not isinstance(self.made, dict):
            raise LinkError(f"{record} is not a record of links. Delete it and run again.")
        if not all(valid_name(name) and isinstance(target, str) for name, target in self.made.items()):
            raise LinkError(f"{record} contains an invalid link name or target; refusing to change links.")

    def ours(self, link):
        """Whether link is a link this script made and nobody changed since."""
        return is_link(link) and self.made.get(link.name) == os.readlink(link)

    def place(self, name, target):
        link = self.folder / name
        if is_link(link):
            if link.exists() and link.samefile(target):
                if not self.ours(link):
                    self.made.pop(name, None)
                return
            if not self.ours(link):
                raise LinkError(
                    f"{link} links to {os.readlink(link)}, not to {target}, and was not made by this script. "
                    "Remove the link and run again."
                )
            remove_link(link)
        elif link.exists():
            if not self.confirm(link):
                raise LinkError(f"{link} is a folder, not a link. Delete it or confirm its replacement, and run again.")
            shutil.rmtree(link)
        create_link(link, target)
        self.made[name] = os.readlink(link)

    def remove_others(self, names):
        """Remove the links this script made that are not among names, and forget the ones that are gone or changed."""
        for name in sorted(set(self.made) - set(names)):
            link = self.folder / name
            if self.ours(link):
                remove_link(link)
            del self.made[name]

    def save(self):
        content = json.dumps(self.made, indent=2, sort_keys=True) + "\n"
        if not self.record.exists() or self.record.read_text(encoding="utf-8") != content:
            self.record.write_text(content, encoding="utf-8")


def link_addons(source, modules, addons, confirm=ask_to_replace):
    """Link each Odoo addon in addons and each module in the modules folder into source/odoo/addons."""
    addons_folder = source / "odoo" / "addons"
    if not addons_folder.is_dir():
        raise LinkError(f"{addons_folder} not found. Run: task dev:odoo-source")
    if not all(valid_name(name) for name in addons):
        raise LinkError("Addon names must be single directory names; refusing to change links.")
    targets = {name: source / "addons" / name for name in addons}
    targets |= {path.name: path for path in sorted(modules.iterdir()) if (path / MANIFEST).is_file()}
    for target in targets.values():
        if not target.is_dir():
            raise LinkError(f"{target} not found. Run: task dev:odoo-source")
    links = Links(addons_folder, source / RECORD, confirm)
    try:
        for name, target in targets.items():
            links.place(name, target.resolve())
        links.remove_others(targets)
    finally:
        links.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="the Odoo source folder")
    parser.add_argument("modules", type=Path, help="the folder of the MediLab modules")
    parser.add_argument("addons", nargs="*", help="the Odoo addons in <source>/addons to link")
    args = parser.parse_args()
    try:
        link_addons(args.source, args.modules, args.addons)
    except LinkError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()

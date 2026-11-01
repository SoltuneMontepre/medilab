"""Files shipped in the folders of installed modules, found by their content."""

import hashlib
import os

from odoo.modules.module import get_module_path


def by_checksum(module_names, wanted):
    """Path of a module file for each SHA-1 of `wanted`, a set of (size, SHA-1) pairs. Only files of a wanted size
    are read, so most files are skipped by their size alone; a file that cannot be read is skipped."""
    sizes = {size for size, _checksum in wanted}
    checksums = {checksum for _size, checksum in wanted}
    found = {}
    for name in module_names:
        root = get_module_path(name, display_warning=False)
        if not root:
            continue
        for folder, _folders, files in os.walk(root):
            for file_name in files:
                path = os.path.join(folder, file_name)
                try:
                    if os.path.getsize(path) not in sizes:
                        continue
                    with open(path, "rb") as file:
                        checksum = hashlib.sha1(file.read()).hexdigest()
                except OSError:
                    # A broken link or an unreadable file holds nothing to restore from.
                    continue
                if checksum in checksums:
                    found.setdefault(checksum, path)
    return found

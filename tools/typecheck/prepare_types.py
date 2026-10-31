"""Prepare owned, source-matched Odoo typing artifacts for this checkout.

Run from any directory: python tools/typecheck/prepare_types.py [--image <image>].
The default image tag belongs to this checkout; an explicit image is inspected without retagging it.
"""

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from analysis_overlay import prepare as prepare_analysis
from artifacts import artifact_hashes, validate
from prepare_registry import prepare as prepare_registry
from typing_inputs import fingerprint

ROOT = Path(__file__).resolve().parents[2]
OWNER_FILE = "build.json"


def command(*arguments, capture=False):
    executable = shutil.which(arguments[0])
    if executable is None:
        raise RuntimeError(f"{arguments[0]} is required to prepare Odoo typing.")
    return subprocess.run(
        [executable, *arguments[1:]],
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )


def image_id(image):
    return command(
        "docker", "image", "inspect", image, "--format", "{{.Id}}", capture=True
    ).stdout.strip()


def private_image(root):
    digest = hashlib.sha256()
    for relative in (
        "tools/dockerfiles/prod.dockerfile",
        "src/core/pyproject.toml",
        "src/core/uv.lock",
        "src/core/config/odoo.conf",
    ):
        digest.update((root / relative).read_bytes())
    workspace = hashlib.sha256(
        os.path.normcase(str(root.resolve())).encode()
    ).hexdigest()[:12]
    return f"medilab-typecheck-{workspace}:{digest.hexdigest()[:16]}"


def ensure_image(root, explicit):
    image = explicit or private_image(root)
    try:
        return image, image_id(image)
    except subprocess.CalledProcessError:
        command(
            "docker",
            "build",
            "--file",
            str(root / "tools/dockerfiles/prod.dockerfile"),
            "--tag",
            image,
            str(root),
        )
        return image, image_id(image)


def owned(path, root):
    if path.is_symlink() or path.is_junction():
        raise RuntimeError(f"Refusing to replace a linked typing directory: {path}")
    marker = json.loads((path / OWNER_FILE).read_text(encoding="utf-8"))
    if marker.get("workspace") != os.path.normcase(
        str(root.resolve())
    ) or not marker.get("owner"):
        raise RuntimeError(f"Refusing to replace an unowned typing directory: {path}")


def publish(stage, target, root):
    previous = target.with_name(f".previous-{uuid.uuid4().hex}")
    if target.exists():
        owned(target, root)
        target.rename(previous)
    try:
        stage.rename(target)
    except BaseException:
        if previous.exists():
            previous.rename(target)
        raise
    if previous.exists():
        shutil.rmtree(previous)


@contextlib.contextmanager
def preparation_lock(directory):
    path = directory / "prepare.lock"
    owner = uuid.uuid4().hex
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"owner": owner, "pid": os.getpid()}, stream)
    except FileExistsError as error:
        raise RuntimeError(
            f"Typing preparation is already locked: {path}. Check its owner before removing it."
        ) from error
    try:
        yield owner
    finally:
        if json.loads(path.read_text(encoding="utf-8")).get("owner") != owner:
            raise RuntimeError(f"The typing preparation lock changed ownership: {path}")
        path.unlink()


def prepare(root, image=None):
    directory = root / ".local/typecheck"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "current"
    with preparation_lock(directory) as owner:
        command(
            "git",
            "-C",
            str(root / ".local/odoo-source"),
            "sparse-checkout",
            "add",
            "addons",
        )
        _, identifier = ensure_image(root, image)
        if target.exists():
            owned(target, root)
            try:
                marker = validate(root, target)
                if marker["image"] != identifier:
                    raise ValueError("The typing image changed.")
                print("Odoo typing is current.")
                return
            except (OSError, ValueError):
                pass
        inputs = fingerprint(root, identifier)
        stage = directory / f".prepare-{owner}"
        registry = stage / "registry"
        prepare_registry(identifier, registry)
        analysis = stage / "analysis"
        prepare_analysis(root, registry, analysis, published_path=target)
        for name in ("registry.json", "xmlids.json", "source-hashes.json"):
            shutil.copyfile(registry / name, analysis / name)
        if fingerprint(root, identifier) != inputs:
            raise RuntimeError(
                "Source inputs changed during typing preparation; rerun task typecheck."
            )
        (analysis / "inputs.json").write_text(
            json.dumps(inputs, indent=2) + "\n", encoding="utf-8"
        )
        (analysis / OWNER_FILE).write_text(
            json.dumps(
                {
                    "workspace": os.path.normcase(str(root.resolve())),
                    "owner": owner,
                    "image": identifier,
                    "artifacts": artifact_hashes(analysis),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        publish(analysis, target, root)
        shutil.rmtree(stage)
    print("Odoo typing prepared.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=os.environ.get("MEDILAB_ODOO_IMAGE"))
    args = parser.parse_args()
    prepare(ROOT, args.image)


if __name__ == "__main__":
    main()

"""Install a registry in disposable, labelled Docker resources and export its typing metadata.

Run from any directory: python tools/typecheck/prepare_registry.py --image <Odoo image>.
No host ports or application volumes are used. Every run owns a distinct PostgreSQL container.
"""

import argparse
import hashlib
import json
import secrets
import subprocess
import time
import uuid
from pathlib import Path

from typing_inputs import fingerprint

ROOT = Path(__file__).resolve().parents[2]
OWNER_LABEL = "org.medilab.typecheck.owner"
CORE_FILES = (
    "orm/models.py",
    "orm/environments.py",
    "orm/fields.py",
    "orm/fields_misc.py",
    "orm/fields_selection.py",
    "orm/fields_relational.py",
    "orm/fields_binary.py",
    "tests/common.py",
    "tests/form.py",
    "tools/misc.py",
    "tools/sql.py",
    "http/requestlib.py",
    "http/routing_map.py",
)


def run(*arguments, capture=False, **kwargs):
    return subprocess.run(
        list(arguments),
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        **kwargs,
    )


def remove_owned(kind, name, owner):
    inspected = run("docker", kind, "inspect", name, capture=True)
    resource = json.loads(inspected.stdout)[0]
    labels = (
        (resource.get("Labels") or resource.get("labels"))
        if kind == "network"
        else resource["Config"].get("Labels")
    )
    if (labels or {}).get(OWNER_LABEL) != owner:
        raise RuntimeError(f"Refusing to remove unowned {kind}: {name}")
    arguments = ["docker", kind, "rm"]
    if kind == "container":
        arguments.extend(["--force", "--volumes"])
    run(*arguments, name)


def verify_core(image):
    script = (
        "import json,hashlib; from pathlib import Path; import odoo.orm.environments; "
        "root=Path(odoo.orm.environments.__file__).parents[1]; "
        f"print(json.dumps({{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in {CORE_FILES!r}}}))"
    )
    actual = json.loads(
        run(
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "python3",
            image,
            "-c",
            script,
            capture=True,
        ).stdout
    )
    for name in CORE_FILES:
        expected = hashlib.sha256(
            (ROOT / ".local/odoo-source/odoo" / name).read_bytes()
        ).hexdigest()
        if actual.get(name) != expected:
            raise RuntimeError(
                f"The Odoo image differs from the pinned analysis source: {name}"
            )


def verify_method_sources(output):
    hashes = json.loads((output / "source-hashes.json").read_text(encoding="utf-8"))
    if not hashes:
        raise RuntimeError("The registry exported no native method source hashes.")
    original = ROOT / ".local/odoo-source"
    for relative, expected in hashes.items():
        name = Path(relative)
        if name.is_absolute() or ".." in name.parts:
            raise ValueError(f"Invalid Odoo source path: {relative}")
        source = original / "odoo" / name
        if not source.is_file() and name.parts[0] == "addons":
            source = original / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise RuntimeError(
                f"Registry method source differs from the pinned analysis source: {relative}"
            )


def prepare(image, output):
    owner = uuid.uuid4().hex
    database_password = secrets.token_urlsafe(32)
    prefix = f"medilab-typecheck-{owner}"
    network, postgres = f"{prefix}-net", f"{prefix}-db"
    image_id = run(
        "docker", "image", "inspect", image, "--format", "{{.Id}}", capture=True
    ).stdout.strip()
    verify_core(image_id)
    output.mkdir(parents=True, exist_ok=False)
    inputs = fingerprint(ROOT, image_id)
    created = []
    odoo_name = f"{prefix}-odoo"
    owner_path = output / "owner.json"
    ownership = {
        "owner": owner,
        "network": network,
        "postgres": postgres,
        "odoo": odoo_name,
        "state": "preparing",
    }
    owner_path.write_text(json.dumps(ownership, indent=2) + "\n", encoding="utf-8")
    try:
        run("docker", "network", "create", "--label", f"{OWNER_LABEL}={owner}", network)
        created.append(("network", network))
        run(
            "docker",
            "run",
            "--detach",
            "--name",
            postgres,
            "--network",
            network,
            "--label",
            f"{OWNER_LABEL}={owner}",
            "--env",
            f"POSTGRES_PASSWORD={database_password}",
            "--env",
            "POSTGRES_USER=typecheck",
            "--env",
            "POSTGRES_DB=typecheck",
            "postgres:18.4",
        )
        created.append(("container", postgres))
        for _ in range(60):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    postgres,
                    "pg_isready",
                    "-U",
                    "typecheck",
                    "-d",
                    "typecheck",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("The disposable typing database did not become ready.")
        modules = ",".join((ROOT / "src/core/modules.txt").read_text().split())
        common = [
            "docker",
            "run",
            "--rm",
            "--name",
            odoo_name,
            "--interactive",
            "--network",
            network,
            "--user",
            "root",
            "--env",
            f"MEDILAB_TYPECHECK_MODULES={modules}",
            "--label",
            f"{OWNER_LABEL}={owner}",
            "--volume",
            f"{ROOT / 'src/core/modules'}:/mnt/extra-addons:ro",
            "--volume",
            f"{output}:/output",
            "--entrypoint",
            "python3",
            image_id,
            "-m",
            "odoo",
        ]
        options = [
            "--db_host",
            postgres,
            "--db_user",
            "typecheck",
            "--db_password",
            database_password,
            "--database",
            "typecheck",
            "--data-dir",
            "/var/lib/odoo/typecheck-data",
            "--stop-after-init",
            "--without-demo",
            "True",
            "--no-http",
        ]
        run(*common, *options, "--init", "base")
        run(
            *common,
            "shell",
            *options,
            input=(ROOT / "tools/scripts/demo_bootstrap_set_country.py").read_text(),
        )
        run(*common, *options, "--init", "l10n_vn")
        run(
            *common,
            "shell",
            *options,
            input=(ROOT / "tools/scripts/demo_bootstrap_accounting.py").read_text(),
        )
        run(*common, *options, "--init", modules)
        run(
            *common,
            "shell",
            *options,
            input=Path(__file__).with_name("registry_export.py").read_text(),
        )
        snapshot = json.loads((output / "registry.json").read_text())
        verify_method_sources(output)
        if not snapshot:
            raise RuntimeError("Odoo exported an empty registry.")
        (output / "image.json").write_text(json.dumps({"image": image_id}) + "\n")
        if fingerprint(ROOT, image_id) != inputs:
            raise RuntimeError(
                "Source inputs changed during installation; regenerate the typing registry."
            )
        (output / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    finally:
        names = run(
            "docker", "container", "ls", "--all", "--format", "{{.Names}}", capture=True
        ).stdout.splitlines()
        if odoo_name in names:
            remove_owned("container", odoo_name, owner)
        for kind, name in reversed(created):
            remove_owned(kind, name, owner)
        ownership["state"] = "cleaned"
        owner_path.write_text(json.dumps(ownership, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".local/typecheck/registry"
    )
    args = parser.parse_args()
    prepare(args.image, args.output.resolve())


if __name__ == "__main__":
    main()

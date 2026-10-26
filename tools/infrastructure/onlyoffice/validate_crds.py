"""Validate custom resources against supplied pinned upstream CRDs without cluster access."""

import argparse
import sys
from pathlib import Path

import jsonschema
import yaml
from operator_files import read_input, trusted_roots

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--crd", action="append", required=True)
    parser.add_argument("manifests", nargs="+")
    parser.add_argument("--skip-kind", action="append", default=[])
    args = parser.parse_args()
    roots = trusted_roots("MEDILAB_ONLYOFFICE_SCHEMA_ROOTS", (ROOT,))
    schemas = {}
    for filename in args.crd:
        for resource in yaml.safe_load_all(read_input(filename, roots, 64 * 1024 * 1024).decode("utf-8")):
            if not resource or resource.get("kind") != "CustomResourceDefinition":
                continue
            spec = resource["spec"]
            for version in spec["versions"]:
                schemas[spec["group"] + "/" + version["name"], spec["names"]["kind"]] = version["schema"][
                    "openAPIV3Schema"
                ]
    count = 0
    for filename in args.manifests:
        for resource in yaml.safe_load_all(read_input(filename, roots, 64 * 1024 * 1024).decode("utf-8")):
            if not resource or resource["apiVersion"] in (
                "v1",
                "apps/v1",
                "networking.k8s.io/v1",
                "batch/v1",
            ):
                continue
            if resource["kind"] in args.skip_kind:
                continue
            schema = schemas[resource["apiVersion"], resource["kind"]]
            jsonschema.Draft7Validator(schema).validate(resource)
            count += 1
    sys.stdout.write(f"Validated {count} custom resources against upstream schemas.\n")


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        yaml.YAMLError,
        jsonschema.ValidationError,
    ):
        sys.stderr.write("CRD validation failed; check trusted inputs and pinned schema compatibility.\n")
        sys.exit(1)

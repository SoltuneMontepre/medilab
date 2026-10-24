"""test:openapi: refuse a YAML document in which a mapping has the same key twice. YAML loaders keep the last value of
a duplicate key, so the document still parses and validates without it.

Usage: test_openapi_keys.py <document in the repository>
"""

import pathlib
import sys

import yaml

REPOSITORY = pathlib.Path(__file__).resolve().parents[2]


def mapping_duplicates(node):
    """The (key, line, line of its first use) of each scalar key that repeats in one mapping node."""
    found = []
    first = {}
    for key, _value in node.value:
        if not isinstance(key, yaml.ScalarNode):
            continue
        line = key.start_mark.line + 1
        if key.value in first:
            found.append((key.value, line, first[key.value]))
        else:
            first[key.value] = line
    return found


def duplicate_keys(text):
    """The (key, line of the repeated key, line of its first use) of every duplicate key, lines counted from 1."""
    found = []
    nodes = [yaml.compose(text, Loader=yaml.SafeLoader)]
    while nodes:
        node = nodes.pop()
        if isinstance(node, yaml.MappingNode):
            found.extend(mapping_duplicates(node))
            nodes.extend(value for _key, value in node.value)
        elif isinstance(node, yaml.SequenceNode):
            nodes.extend(node.value)
    return sorted(found, key=lambda duplicate: duplicate[1])


def main(document):
    path = (REPOSITORY / document).resolve()
    if not path.is_relative_to(REPOSITORY):
        print(f"{document} is outside the repository.")
        return 2
    duplicates = duplicate_keys(path.read_text(encoding="utf-8"))
    for key, line, first in duplicates:
        print(f"{document}:{line}: key {key} is already defined on line {first}.")
    return 1 if duplicates else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))

"""test:openapi: refuse a YAML document in which a mapping has the same key twice. YAML loaders keep the last value of
a duplicate key, so the document still parses and validates without it.

Usage: yaml_duplicate_keys.py <document>
"""

import pathlib
import sys

import yaml


def duplicate_keys(text):
    """The (key, line of the repeated key, line of its first use) of every duplicate key, lines counted from 1."""
    found = []
    nodes = [yaml.compose(text, Loader=yaml.SafeLoader)]
    while nodes:
        node = nodes.pop()
        if isinstance(node, yaml.MappingNode):
            first = {}
            for key, value in node.value:
                if isinstance(key, yaml.ScalarNode):
                    line = key.start_mark.line + 1
                    if key.value in first:
                        found.append((key.value, line, first[key.value]))
                    else:
                        first[key.value] = line
                nodes.append(value)
        elif isinstance(node, yaml.SequenceNode):
            nodes.extend(node.value)
    return sorted(found, key=lambda duplicate: duplicate[1])


def main(document):
    duplicates = duplicate_keys(pathlib.Path(document).read_text(encoding="utf-8"))
    for key, line, first in duplicates:
        print(f"{document}:{line}: key {key} is already defined on line {first}.")
    return 1 if duplicates else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))

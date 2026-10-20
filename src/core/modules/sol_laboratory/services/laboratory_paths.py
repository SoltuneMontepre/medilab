"""Checks that the names and patterns laboratory folders receive are names, never a path on someone's computer."""

import re

# A separator, a drive such as C:, or a character no file name holds.
NOT_IN_A_NAME = re.compile(r"[/\\:\x00-\x1f\x7f]")
# The wildcards of a name pattern other than *, which sync rules do not support.
OTHER_WILDCARDS = re.compile(r"[?\[\]{}]")
# An extension as rules keep it, such as csv or tar.gz.
EXTENSION = re.compile(r"[a-z0-9]+(\.[a-z0-9]+)*")


def is_name(text):
    """One file or folder name, such as HPLC or run-01.csv: no separator, drive, home folder or parent folder."""
    if not text or text != text.strip() or text in (".", "..") or text.startswith("~"):
        return False
    return not NOT_IN_A_NAME.search(text)


def is_name_prefix(text):
    return is_name(text) and "*" not in text and not OTHER_WILDCARDS.search(text)


def is_name_pattern(text):
    return is_name(text) and not OTHER_WILDCARDS.search(text)


def is_extension(text):
    return bool(EXTENSION.fullmatch(text))


def normal_extension(text):
    """An extension as rules keep it: without its dot and in lowercase, so a file matches it whatever its case."""
    return text.removeprefix(".").lower()

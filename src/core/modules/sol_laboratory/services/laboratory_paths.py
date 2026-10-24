"""Checks that the names, paths and patterns laboratory folders receive are relative, never a path on someone's
computer, and the one form they are kept in."""

import re
import unicodedata

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


def is_relative_path(text):
    """A path relative to a folder, such as HPLC/run-01.csv: names separated by /, without a root or a drive."""
    return bool(text) and all(is_name(name) for name in text.split("/"))


def normal_text(text):
    """A name, path or pattern in one Unicode form, so a Vietnamese name typed on two computers is the same text."""
    return unicodedata.normalize("NFC", text) if text else text


def path_key(path):
    """What makes two paths one file: the same path in one Unicode form, whatever the letter case."""
    return normal_text(path).casefold()

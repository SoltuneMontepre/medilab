"""Descriptor-anchored operator files beneath explicitly trusted directories."""

import os
import stat
from contextlib import contextmanager
from pathlib import Path

DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def trusted_roots(variable, default=()):
    configured = os.environ.get(variable)
    roots = tuple(Path(value) for value in configured.split(os.pathsep)) if configured else tuple(default)
    if not roots or any(not root.is_absolute() or root == Path("/") for root in roots):
        raise ValueError("Configure explicit absolute trusted directories.")
    return roots


def check_owner(metadata, private=False):
    if metadata.st_uid not in (0, os.geteuid()) or metadata.st_mode & 0o022:
        raise ValueError("Operator files must not be writable by other accounts.")
    if private and metadata.st_mode & 0o077:
        raise ValueError("Secret and evidence files must be private.")


@contextmanager
def directory_at(parent, components):
    descriptor = os.dup(parent)
    try:
        for component in components:
            child = os.open(component, DIRECTORY, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            check_owner(os.fstat(descriptor))
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def parent_directory(value, roots):
    candidate = Path(value).absolute()
    if ".." in candidate.parts or candidate != candidate.resolve(strict=False):
        raise ValueError("Use physical paths without traversal or symbolic links.")
    for root in roots:
        if root != root.resolve(strict=True) or not candidate.is_relative_to(root):
            continue
        relative = candidate.relative_to(root)
        if not relative.parts:
            raise ValueError("Select a file or new child directory within a trusted root.")
        # Pin the root and each child before using an operator-supplied final name.
        descriptor = os.open("/", DIRECTORY)
        try:
            for component in root.parts[1:]:
                child = os.open(component, DIRECTORY, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            check_owner(os.fstat(descriptor))
            with directory_at(descriptor, relative.parts[:-1]) as parent:
                yield parent, relative.name
            return
        finally:
            os.close(descriptor)
    raise ValueError("Operator path is outside the configured trusted directories.")


def read_input(value, roots, limit, private=False):
    with parent_directory(value, roots) as (parent, name):
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
                raise ValueError("Operator input must be a bounded regular file.")
            check_owner(metadata, private)
            content = stream.read(limit + 1)
            if len(content) > limit:
                raise ValueError("Operator input exceeds its limit.")
            return content


@contextmanager
def new_evidence_directory(value, roots):
    with parent_directory(value, roots) as (parent, name):
        os.mkdir(name, mode=0o700, dir_fd=parent)
        descriptor = os.open(name, DIRECTORY, dir_fd=parent)
        try:
            check_owner(os.fstat(descriptor), private=True)
            yield descriptor
        finally:
            os.close(descriptor)


@contextmanager
def new_evidence_file(directory, name):
    if name not in ("document.bin", "evidence.json"):
        raise ValueError("Unknown evidence filename.")
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=directory,
    )
    with os.fdopen(descriptor, "wb") as stream:
        yield stream

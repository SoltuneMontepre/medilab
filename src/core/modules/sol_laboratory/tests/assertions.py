"""Assert optional ORM values before using operations that require their concrete Python type."""

from unittest import TestCase


def assert_instance[ValueT](value: object, kind: type[ValueT]) -> ValueT:
    if not isinstance(value, kind):
        TestCase().fail(f"Expected {kind.__name__}, got {type(value).__name__}.")
    return value

"""Validate values at operations whose input type excludes an empty ORM field."""


def value_as[ValueT](value: object, kind: type[ValueT]) -> ValueT:
    if not isinstance(value, kind):
        raise TypeError(f"Expected {kind.__name__}, got {type(value).__name__}.")
    return value

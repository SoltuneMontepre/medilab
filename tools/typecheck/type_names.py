"""Stable Python symbols for registry model names."""

import re


def model_type(name):
    return "Model_" + re.sub(r"\W", "_", name)

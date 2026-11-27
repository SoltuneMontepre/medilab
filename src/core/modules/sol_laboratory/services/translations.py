"""Text kept as it was written, in every language, for a translated field that never follows later changes."""

from collections.abc import Callable

from odoo.api import Environment

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_LANG


def in_every_language(env: Environment, text_of: Callable[[str], str]) -> dict[str, str]:
    """The text in each installed language, from a function of the language's code, to write to a translated field so
    that whoever reads it later reads their own language."""
    return {code: text_of(code) for code, _name in env[MODEL_RES_LANG].get_installed()}

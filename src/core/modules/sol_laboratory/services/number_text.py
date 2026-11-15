"""Numbers written with the decimals they have, in the person's language."""

from decimal import Decimal

from odoo.tools import formatLang


def plain_digits(number):
    """The decimals the number has as written, such as 2 for 0.01 and 0 for 3.0."""
    return max(0, -int(Decimal(repr(float(number))).normalize().as_tuple().exponent))


def plain_number(env, number):
    """The number in the language of env with the decimals it has, such as 3 or 2.5."""
    return formatLang(env, number, digits=plain_digits(number))

from odoo import fields


class BigInteger(fields.Integer):
    """An integer kept in 64 bits, for values beyond the 2^31 - 1 of Odoo's integers, such as the size of a 5 GiB file.
    Odoo registers field types by name once, so this class does not replace its integers."""

    _column_type = ("int8", "int8")

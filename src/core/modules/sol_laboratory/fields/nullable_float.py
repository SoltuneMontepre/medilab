from odoo import fields


class NullableFloat(fields.Float):
    """A float that keeps an empty value apart from zero, such as a detection limit that is absent. An empty value
    reads as False and is stored as NULL; zero stays zero."""

    falsy_value = None

    def convert_to_column(self, value, record, values=None, validate=True):
        if value is None or value is False:
            return None
        return super().convert_to_column(value, record, values, validate)

    def convert_to_cache(self, value, records, validate=True):
        if value is None or value is False:
            return None
        return super().convert_to_cache(value, records, validate)

    def convert_to_record(self, value, record):
        return False if value is None else value

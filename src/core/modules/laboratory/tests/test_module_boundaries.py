from odoo.orm.models import MAGIC_COLUMNS
from odoo.tests import TransactionCase, tagged

MODULE = "laboratory"
PREFIX = "medilab."


@tagged("post_install", "-at_install")
class TestModuleBoundaries(TransactionCase):
    def test_other_modules_add_no_stored_column_to_laboratory_tables(self):
        # A module keeps its data in its own tables, so uninstalling it leaves the Laboratory data intact.
        for name, model in self.env.registry.items():
            if not name.startswith(PREFIX) or model._original_module != MODULE or model._abstract or model._transient:
                continue
            foreign = sorted(
                f"{field.name} ({field._module})"
                for field in model._fields.values()
                if field.store
                and field.column_type
                and field.name not in MAGIC_COLUMNS
                and field._module not in (None, MODULE)
            )
            with self.subTest(model=name):
                self.assertEqual(foreign, [])

from lxml import etree

from odoo.modules.module import get_manifest
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE
from odoo.addons.sol_laboratory.services.model_lookup import dynamic_model
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

# Odoo names these itself: the reflection of models and fields, and the server action behind each cron.
GENERATED_MODELS = ("ir.model", "ir.model.fields", "ir.actions.server")


def short_name(model):
    return model.removeprefix("medilab.").replace(".", "_")


@tagged("post_install", "-at_install")
class TestDemoDataConvention(TransactionCase):
    def test_demo_records_live_in_the_file_of_their_model(self):
        declared = set()
        for path in get_manifest("sol_demo")["data"]:
            for node in etree.parse(file_path(f"sol_demo/{path}")).iter("record", "function"):
                model = assert_instance(node.get("model"), str)
                record_id = node.get("id")
                # Records of another module, or declared in an earlier file, are only completed here.
                if record_id and ("." in record_id or record_id in declared):
                    continue
                expected = f"data/{dynamic_model(self.env, model)._original_module}/{short_name(model)}.xml"
                self.assertEqual(path, expected, record_id or model)
                declared.add(record_id)

    def test_every_demo_xml_id_is_named_after_its_model(self):
        self.env[MODEL_ACCOUNT_MOVE]._seed_notification_demo()
        xml_ids = self.env["ir.model.data"].search([("module", "=", "sol_demo"), ("model", "not in", GENERATED_MODELS)])
        self.assertTrue(xml_ids)
        models = dict(zip(xml_ids.mapped("name"), xml_ids.mapped("model"), strict=True))
        for xml_id in xml_ids:
            # Odoo names the parent it creates for a delegated record after the record, such as a product's template.
            child = models.get(
                assert_instance(xml_id.name, str).removesuffix(
                    f"_{assert_instance(xml_id.model, str).replace('.', '_')}"
                )
            )
            if child and xml_id.model in dynamic_model(self.env, child)._inherits:
                continue
            self.assertTrue(
                assert_instance(xml_id.name, str).startswith(f"demo_{short_name(xml_id.model)}_"), xml_id.name
            )

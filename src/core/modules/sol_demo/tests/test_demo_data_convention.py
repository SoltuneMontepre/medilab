from lxml import etree

from odoo.modules.module import get_manifest
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE

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
                model = node.get("model")
                record_id = node.get("id")
                # Records of another module, or declared in an earlier file, are only completed here.
                if record_id and ("." in record_id or record_id in declared):
                    continue
                expected = f"data/{self.env[model]._original_module}/{short_name(model)}.xml"
                self.assertEqual(path, expected, record_id or model)
                declared.add(record_id)

    def test_every_demo_xml_id_is_named_after_its_model(self):
        self.env[MODEL_ACCOUNT_MOVE]._seed_notification_demo()
        xml_ids = self.env["ir.model.data"].search([("module", "=", "sol_demo"), ("model", "not in", GENERATED_MODELS)])
        self.assertTrue(xml_ids)
        for xml_id in xml_ids:
            self.assertTrue(xml_id.name.startswith(f"demo_{short_name(xml_id.model)}_"), xml_id.name)

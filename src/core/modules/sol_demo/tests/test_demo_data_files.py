from lxml import etree

from odoo.modules.module import get_manifest
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path


@tagged("post_install", "-at_install")
class TestDemoDataFiles(TransactionCase):
    def test_demo_records_live_in_their_model_file_with_a_demo_id(self):
        declared = set()
        for path in get_manifest("sol_demo")["data"]:
            for node in etree.parse(file_path(f"sol_demo/{path}")).iter("record", "function"):
                model = node.get("model")
                record_id = node.get("id")
                # Records of another module, or declared in an earlier file, are only updated here.
                if record_id and ("." in record_id or record_id in declared):
                    continue
                name = model.removeprefix("medilab.").replace(".", "_")
                self.assertEqual(path, f"data/{self.env[model]._original_module}/{name}.xml", record_id or model)
                if record_id:
                    self.assertTrue(record_id.startswith(f"demo_{name}_"), record_id)
                    declared.add(record_id)

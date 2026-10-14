from lxml import etree

from odoo.modules.module import get_manifest
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

from odoo.addons.sol_laboratory.constants.models import MASTER_DATA_MODELS


@tagged("post_install", "-at_install")
class TestMasterDataDemoFiles(TransactionCase):
    def test_master_data_records_live_in_their_model_file_with_a_demo_id(self):
        checked = set()
        for path in get_manifest("sol_demo")["data"]:
            for record in etree.parse(file_path(f"sol_demo/{path}")).iterfind("record"):
                model = record.get("model")
                if model not in MASTER_DATA_MODELS:
                    continue
                name = model.removeprefix("medilab.").replace(".", "_")
                self.assertEqual(path, f"data/sol_laboratory/{name}.xml")
                self.assertTrue(record.get("id").startswith(f"demo_{name}_"), record.get("id"))
                checked.add(model)
        self.assertEqual(checked, set(MASTER_DATA_MODELS))

from base64 import b64encode
from pathlib import Path

from lxml import etree

from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.tools.binary import BinaryValue
from odoo.tools.misc import file_open

from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestDemoBinaryData(TransactionCase):
    def test_demo_images_load_as_bytes_without_changing_their_contents(self):
        data = (
            ("data/base/res_partner.xml", "demo_res_partner_nuoc_sach", "image_1920", "logo_nuoc_sach.png"),
            ("data/sol_laboratory/location.xml", "demo_location_floor_1", "image", "floor_plan_1.svg"),
        )
        module_dir = Path(__file__).resolve().parents[1]

        for data_path, record_id, field_name, file_name in data:
            with self.subTest(record=record_id):
                xml = etree.parse(module_dir / data_path)
                binary_field = xml.find(f'.//record[@id="{record_id}"]/field[@name="{field_name}"]')
                assert binary_field is not None, f"Missing {field_name} on {record_id}"
                self.assertEqual(binary_field.get("type"), "bytes")

                with file_open(f"sol_demo/static/img/{file_name}", "rb") as expected_file:
                    expected = expected_file.read()
                record = self.env.ref(f"sol_demo.{record_id}")
                field = assert_instance(record._fields[field_name], fields.Image)
                processed = field._image_process(b64encode(expected).decode(), record.env)
                self.assertEqual(record[field_name].content, assert_instance(processed, BinaryValue).content)

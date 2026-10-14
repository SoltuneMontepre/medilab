from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP


@tagged("post_install", "-at_install")
class TestBlindTesting(RequestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        reader = "sol_laboratory.group_permission_{}_read_all"
        cls.tester = new_test_user(
            cls.env,
            login="tester",
            groups=f"base.group_user,{reader.format('sample')},{reader.format('sample_test')}",
        )
        cls.delivery_staff = new_test_user(
            cls.env,
            login="delivery.staff",
            groups=f"base.group_user,{reader.format('sample')},{TEST_REQUEST_READER_GROUP}",
        )

    def test_tester_reads_a_sample_only_by_its_lab_code(self):
        sample = self.sample.with_user(self.tester)

        self.assertEqual(sample.code, self.sample.code)
        self.assertEqual(sample.test_ids.parameter_id, self.parameter)
        with self.assertRaises(AccessError):
            sample.read(["customer_sample_name"])
        with self.assertRaises(AccessError):
            sample.search([("customer_sample_name", "ilike", "Lavie")])
        with self.assertRaises(AccessError):
            sample.request_id.read(["customer_id"])

    def test_tester_views_leave_out_the_customer(self):
        views = (
            self.env[MODEL_SAMPLE]
            .with_user(self.tester)
            .get_views([(False, "list"), (False, "form"), (False, "search")])
        )

        for view_type, view in views["views"].items():
            with self.subTest(view=view_type):
                self.assertNotIn("customer_sample_name", view["arch"])
                self.assertNotIn("ir.attachment", view["arch"])

    def test_tester_cannot_read_a_sample_photo(self):
        photo = self.env["ir.attachment"].create(
            {
                "name": "bottle.jpg",
                "raw": b"photo",
                "mimetype": "image/jpeg",
                "res_model": MODEL_SAMPLE,
                "res_id": self.sample.id,
            }
        )

        with self.assertRaises(AccessError):
            photo.with_user(self.tester).read(["name"])
        self.assertFalse(self.env["ir.attachment"].with_user(self.tester).search([("id", "=", photo.id)]))
        self.assertEqual(photo.with_user(self.delivery_staff).name, "bottle.jpg")

    def test_who_reads_test_requests_sees_the_customer(self):
        sample = self.sample.with_user(self.delivery_staff)

        self.assertEqual(sample.customer_sample_name, "Lavie bottled water 1 L")
        self.assertEqual(sample.request_id.customer_id, self.customer)

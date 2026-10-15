from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP


@tagged("post_install", "-at_install")
class TestSamplePhoto(RequestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        reader = "sol_laboratory.group_permission_{}_read_all"
        cls.tester = new_test_user(cls.env, login="photo.tester", groups=f"base.group_user,{reader.format('sample')}")
        cls.reader = new_test_user(
            cls.env,
            login="photo.reader",
            groups=f"base.group_user,{reader.format('sample')},{TEST_REQUEST_READER_GROUP}",
        )

    def test_a_photo_from_the_mobile_app_appears_on_the_sample(self):
        photo = self.sample.action_attach_photo(b"\x89PNG\r\n\x1a\nphoto", "collected.png")

        self.assertEqual(self.sample.with_user(self.reader).photo_ids, photo)
        self.assertEqual((photo.res_model, photo.res_id), (MODEL_SAMPLE, self.sample.id))

    def test_a_sample_photo_is_readable_by_a_test_request_reader_and_not_by_a_tester(self):
        photo = self.env["ir.attachment"].create(
            {
                "name": "bottle.jpg",
                "raw": b"photo",
                "mimetype": "image/jpeg",
                "res_model": MODEL_SAMPLE,
                "res_id": self.sample.id,
            }
        )

        self.assertEqual(photo.with_user(self.reader).name, "bottle.jpg")
        with self.assertRaises(AccessError):
            photo.with_user(self.tester).read(["name"])
        self.assertFalse(self.env["ir.attachment"].with_user(self.tester).search([("id", "=", photo.id)]))

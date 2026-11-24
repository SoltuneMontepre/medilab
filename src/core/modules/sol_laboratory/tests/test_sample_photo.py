from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REQUEST_READER_GROUP
from odoo.addons.sol_laboratory.services.record_id import persisted_id


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
        cls.delivery = new_test_user(
            cls.env,
            login="photo.delivery",
            groups=(
                f"base.group_user,{reader.format('sample')},{TEST_REQUEST_READER_GROUP},"
                "sol_laboratory.group_permission_sample_create_all"
            ),
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

    def test_delivery_can_attach_a_collection_photo_without_editing_the_photo_relation(self):
        sample = self.sample.with_user(self.delivery)
        photo = sample.action_attach_photo(b"\x89PNG\r\n\x1a\nphoto", "collected.png")

        self.assertEqual(sample.photo_ids, photo)
        self.assertEqual((photo.res_model, photo.res_id), (MODEL_SAMPLE, sample.id))
        with self.assertRaises(AccessError):
            sample.write({"photo_ids": [Command.unlink(persisted_id(photo))]})
        self.assertEqual(sample.photo_ids, photo)

    def test_collection_photo_permission_ends_after_reception(self):
        self.sample.status = "testing"
        with self.assertRaises(AccessError):
            self.sample.with_user(self.delivery).action_attach_photo(b"\x89PNG\r\n\x1a\nphoto", "testing.png")

        self.assertFalse(self.sample.photo_ids)

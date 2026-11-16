import base64
from unittest.mock import patch

from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from .mobile_phones import PhoneCalls, phone_person
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    IDEMPOTENCY_CONFLICT,
    INVALID_REQUEST,
    NOT_FOUND,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.medilab_mobile import TOO_LARGE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_ATTACHMENT,
    MODEL_LABORATORY_DEVICE,
    MODEL_LOCATION,
    MODEL_SAMPLE,
    MODEL_TASK,
)

PHOTO = b"\x89PNG\r\n\x1a\nphoto taken at the customer's site"
# What sample delivery staff may do with samples, as the demo staff may.
STAFF_PERMISSIONS = ("test_request_read_all", "sample_read_all", "sample_edit_all")


def photo_body(photo=PHOTO, name="collected.png"):
    return {"name": name, "mimetype": "image/png", "data": base64.b64encode(photo).decode()}


@tagged("post_install", "-at_install")
class TestMedilabMobilePhotos(PhoneCalls, LaboratoryApiCase, RequestCase):
    """Collecting samples on Medilab Mobile: a member of sample delivery staff sees a collection task with its time and
    place, marks it done and photographs the sample, which a tester never sees."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sample.sampling_location_id = cls.env[MODEL_LOCATION].create({"code": "RO-01", "name": "RO sampling point"})
        cls.staff = phone_person(cls.env, "Le Thi Lan", "lan.photo", None, STAFF_PERMISSIONS)
        cls.tester = phone_person(
            cls.env,
            "Nguyen Van An",
            "an.photo",
            cls.department,
            ("sample_read_all", "sample_handover_read_own_department"),
        )
        # The laboratory received the sample and handed it over to the tester's department.
        staff = cls.env.ref("sol_laboratory.person_administrator")
        cls.sample.with_user(staff.user_id).action_receive("2 bottles of 1 L", "good")
        collection = cls.env.ref("sol_laboratory.task_type_sample_collection")
        cls.collection = cls.env[MODEL_TASK].create(
            {
                "type_id": collection.id,
                "name": "Collect the bottled water",
                "assignee_id": cls.staff.id,
                "planned_start": "2026-12-01 02:00:00",
                "planned_end": "2026-12-01 03:00:00",
                "document_model": MODEL_SAMPLE,
                "document_id": cls.sample.id,
            }
        )

    def attach(self, person, body=None, key="photo-1"):
        return self.on_phone(
            person, "POST", f"/samples/{self.sample.id}/photos", body or photo_body(), {"Idempotency-Key": key}
        )

    # Collection tasks

    def test_staff_see_the_collection_task_with_its_time_place_and_sample_and_mark_it_done(self):
        task = self.answered(self.on_phone(self.staff, "GET", f"/tasks/{self.collection.id}"))
        listed = self.answered(self.on_phone(self.staff, "GET", "/tasks?list=open"))["tasks"]
        done = self.answered(self.on_phone(self.staff, "POST", f"/tasks/{self.collection.id}/done"))

        self.assertEqual(
            (task["planned_start"], task["planned_end"]), ("2026-12-01T02:00:00+00:00", "2026-12-01T03:00:00+00:00")
        )
        self.assertEqual(task["location"], self.sample.sampling_location_id.display_name)
        self.assertEqual(
            task["samples"],
            [{"id": self.sample.id, "code": self.sample.code, "sampling_location": task["location"]}],
        )
        self.assertEqual([each["location"] for each in listed if each["id"] == self.collection.id], [task["location"]])
        self.assertTrue(task["actions"]["done"])
        self.assertEqual((done["status"], self.collection.status), ("done", "done"))

    def test_a_collection_task_of_a_test_request_is_for_the_request_samples(self):
        self.collection.write({"document_model": self.request._name, "document_id": self.request.id})

        task = self.answered(self.on_phone(self.staff, "GET", f"/tasks/{self.collection.id}"))

        self.assertEqual([sample["id"] for sample in task["samples"]], self.request.sample_ids.ids)

    # Photos

    def test_a_photo_taken_on_the_phone_appears_on_the_sample_once_per_idempotency_key(self):
        sample = self.answered(self.on_phone(self.staff, "GET", f"/samples/{self.sample.id}"))
        sent = self.answered(self.attach(self.staff))
        again = self.answered(self.attach(self.staff))
        conflict = self.attach(self.staff, photo_body(b"another photo"))
        listed = self.answered(self.on_phone(self.staff, "GET", f"/samples/{self.sample.id}/photos"))
        downloaded = self.on_phone(self.staff, "GET", f"/attachments/{sent['id']}")

        self.assertTrue(sample["can_add_photos"])
        photo = self.env[MODEL_IR_ATTACHMENT].browse(sent["id"])
        self.assertEqual(again, sent)
        self.assertApiRefused(IDEMPOTENCY_CONFLICT, conflict)
        self.assertEqual(self.sample.photo_ids, photo)
        self.assertEqual((photo.res_model, photo.res_id, bytes(photo.raw)), (MODEL_SAMPLE, self.sample.id, PHOTO))
        phone = self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", f"phone-{self.staff.id}")])
        self.assertEqual(photo.created_by_device_id, phone)
        self.assertEqual(
            (sent["name"], sent["mimetype"], sent["created_by"]), ("collected.png", "image/png", "Le Thi Lan")
        )
        self.assertEqual(listed["photos"], [sent])
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual((downloaded.content, downloaded.headers["Content-Type"]), (PHOTO, "image/png"))

    def test_a_tester_never_sees_or_adds_a_sample_photo(self):
        photo = self.sample.action_attach_photo(PHOTO, "received.png")

        sample = self.answered(self.on_phone(self.tester, "GET", f"/samples/{self.sample.id}"))
        listed = self.answered(self.on_phone(self.tester, "GET", f"/samples/{self.sample.id}/photos"))

        self.assertFalse(sample["can_add_photos"])
        self.assertEqual(listed["photos"], [])
        self.assertApiRefused(NOT_FOUND, self.on_phone(self.tester, "GET", f"/attachments/{photo.id}"))
        self.assertApiRefused(PERMISSION_DENIED, self.attach(self.tester))
        self.assertEqual(self.sample.photo_ids, photo)

    def test_a_photo_over_the_limit_or_not_in_base64_is_refused_and_stores_nothing(self):
        with patch("odoo.addons.sol_laboratory.models.sample_collection.sample_mobile.PHOTO_MAX_BYTES", 16):
            too_large = self.attach(self.staff, photo_body(b"x" * 17), key="photo-large")
            within = self.attach(self.staff, photo_body(b"x" * 16), key="photo-small")
        not_base64 = self.attach(self.staff, {**photo_body(), "data": "not base64!"}, key="photo-text")

        self.assertApiRefused(TOO_LARGE, too_large)
        self.assertEqual(within.status_code, 200, within.text)
        self.assertApiRefused(INVALID_REQUEST, not_base64)
        self.assertEqual([bytes(photo.raw) for photo in self.sample.photo_ids], [b"x" * 16])

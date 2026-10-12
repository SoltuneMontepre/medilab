from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PERMISSION,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_TEST_REQUEST,
)


@tagged("post_install", "-at_install")
class TestTestRequestDeletion(RequestCase):
    def test_administrator_cannot_delete_a_request_sample_or_sample_test(self):
        administrator = self.env.ref("base.user_admin")

        for records in (self.request, self.sample, self.sample.test_ids):
            with self.subTest(model=records._name), self.assertRaises(AccessError):
                records.with_user(administrator).unlink()

    def test_no_delete_or_archive_permission_can_exist(self):
        for document_model in (MODEL_TEST_REQUEST, MODEL_SAMPLE, MODEL_SAMPLE_TEST):
            for action in ("delete", "archive"):
                with self.subTest(model=document_model, action=action), self.assertRaises(ValidationError):
                    self.env[MODEL_PERMISSION].create(
                        {"name": f"{action} {document_model}", "document_model": document_model, "action": action}
                    )

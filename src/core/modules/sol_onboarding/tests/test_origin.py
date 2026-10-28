from datetime import datetime

from odoo.tests import tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_TESTING_FIELD, MODEL_TESTING_METHOD
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_STAGED_RECORD,
)
from odoo.addons.sol_onboarding.constants.onboarding import KIND_TESTING_METHOD
from odoo.addons.sol_onboarding.services.adapters.base import Fetched, StagedValues
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase

PAGE_URL = "https://lab.example/scope"


@tagged("post_install", "-at_install")
class TestOrigin(OnboardingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.field = cls.env[MODEL_TESTING_FIELD].create({"code": "ZZORIGIN", "name": "Origin field"})

    def stage_method(self, code):
        run = self.env[MODEL_ONBOARDING_RUN].create({"requested_by_id": self.admin.id})
        fetched = Fetched(PAGE_URL, "html", b"<p>Scope</p>", datetime(2026, 10, 21, 8, 0, 0))
        snapshot = self.env[MODEL_ONBOARDING_SNAPSHOT]._keep(run, self.source, fetched)
        values = {"code": code, "name": "Origin method", "field_key": ""}
        return self.env[MODEL_ONBOARDING_STAGED_RECORD]._stage(
            snapshot, [StagedValues(KIND_TESTING_METHOD, code, values, "vi_VN")]
        )

    def origin(self, record):
        """The staged records the reader's Origin button opens."""
        action = record.with_user(self.reader).action_open_onboarding_origin()
        return self.env[action["res_model"]].with_user(self.reader).search(action["domain"])

    def test_a_method_created_by_accepting_shows_its_origin(self):
        staged = self.stage_method("ZZ ORIGIN 1:2026")
        staged.field_id = self.field
        staged.with_user(self.admin).action_accept()
        method = self.env[MODEL_TESTING_METHOD].browse(staged.record_id)

        records = self.origin(method)

        self.assertEqual(method.with_user(self.reader).onboarding_origin_count, 1)
        self.assertEqual(records, staged)
        self.assertEqual(records.page_url, PAGE_URL)

    def test_a_staged_record_still_to_review_is_no_origin(self):
        method = self.env[MODEL_TESTING_METHOD].create(
            {"code": "ZZ ORIGIN 2:2026", "name": "Origin method", "field_id": self.field.id}
        )
        staged = self.stage_method("zz origin 2 : 2026")

        self.assertEqual((staged.state, staged.record_id), ("to_review", method.id))
        self.assertEqual(method.onboarding_origin_count, 0)
        self.assertFalse(self.origin(method))

    def test_no_menu_form_or_list_shows_sources(self):
        data = self.env["ir.model.data"].search([("module", "=", "sol_onboarding"), ("model", "=", "ir.ui.view")])
        views = self.env["ir.ui.view"].browse(data.mapped("res_id"))

        self.assertTrue(views)
        for view in views:
            with self.subTest(view=view.name):
                self.assertNotIn("source_id", view.arch_db)

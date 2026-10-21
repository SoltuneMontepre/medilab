from datetime import datetime

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_SAMPLE_TYPE,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_REJECT,
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_STAGED_RECORD,
)
from odoo.addons.sol_onboarding.constants.onboarding import KIND_SAMPLE_TYPE, KIND_TESTING_METHOD
from odoo.addons.sol_onboarding.services.adapters.base import Fetched, StagedValues
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase


@tagged("post_install", "-at_install")
class TestReview(OnboardingCase):
    def setUp(self):
        super().setUp()
        self.run = self.env[MODEL_ONBOARDING_RUN].create({"requested_by_id": self.admin.id})
        self.records = self.env[MODEL_ONBOARDING_STAGED_RECORD]

    def stage(self, kind, **values):
        fetched = Fetched("https://lab.example/a", "html", b"<p>A</p>", datetime(2026, 10, 21, 8, 0, 0))
        snapshot = self.env[MODEL_ONBOARDING_SNAPSHOT]._keep(self.run, self.source, fetched)
        item = StagedValues(kind, values.get("code") or values["name"], values, "vi_VN")
        return self.records._stage(snapshot, [item])

    def sample(self, name="Review sample xyz"):
        return self.stage(KIND_SAMPLE_TYPE, name=name)

    def test_editing_keeps_the_source_value(self):
        staged = self.sample()

        staged.with_user(self.admin).name = "Edited sample"

        self.assertEqual(staged.source_values, {"name": "Review sample xyz"})
        self.assertEqual(staged.edited_values, {"name": "Edited sample"})
        self.assertEqual(staged.name, "Edited sample")
        staged.with_user(self.admin).name = "Review sample xyz"
        self.assertFalse(staged.edited_values)

    def test_the_rejection_keeps_an_optional_reason_and_reopening_returns_it_to_review(self):
        staged = self.sample()
        staged.with_user(self.admin).action_reject("Duplicate")

        self.assertEqual((staged.state, staged.reject_reason), ("rejected", "Duplicate"))
        self.assertEqual(staged.reviewed_by_id, self.admin)
        self.assertTrue(staged.reviewed_at)

        staged.with_user(self.admin).action_reopen()

        self.assertEqual(
            (staged.state, staged.reject_reason, staged.reviewed_by_id, staged.reviewed_at),
            ("to_review", False, self.env["res.users"], False),
        )
        staged.with_user(self.admin).action_reject(False)
        self.assertEqual((staged.state, staged.reject_reason), ("rejected", False))

    def test_rejecting_many_at_once(self):
        first, second = self.sample("Review one xyz"), self.sample("Review two xyz")
        wizard = (
            self.env[MODEL_ONBOARDING_REJECT]
            .with_user(self.admin)
            .with_context(active_model=MODEL_ONBOARDING_STAGED_RECORD, active_ids=(first | second).ids)
            .create({"reason": "Not needed"})
        )
        self.assertEqual(wizard.staged_record_ids, first | second)

        wizard.action_confirm()

        self.assertEqual((first | second).mapped("state"), ["rejected", "rejected"])
        self.assertEqual((first | second).mapped("reject_reason"), ["Not needed", "Not needed"])

    def test_only_records_to_review_are_rejected(self):
        staged = self.sample()
        staged.state = "accepted"

        with self.assertRaises(UserError):
            staged.with_user(self.admin).action_reject(False)
        with self.assertRaises(UserError):
            staged.with_user(self.admin).action_reopen()
        self.assertEqual(staged.state, "accepted")

    def test_without_the_edit_permission_nothing_changes(self):
        staged = self.sample()

        with self.assertRaises(AccessError):
            staged.with_user(self.reader).action_reject("No")
        with self.assertRaises(AccessError):
            staged.with_user(self.reader).write({"edited_values": {"name": "X"}})
        with self.assertRaises(AccessError):
            staged.with_user(self.reader).name = "X"
        with self.assertRaises(AccessError):
            staged.with_user(self.reader).action_confirm_match()
        self.assertEqual((staged.state, staged.edited_values), ("to_review", False))

    def test_an_update_shows_current_and_new_values(self):
        field = self.env[MODEL_TESTING_FIELD].create({"code": "ZZREVIEW", "name": "Review field"})
        method = self.env[MODEL_TESTING_METHOD].create(
            {"field_id": field.id, "code": "TCVN 9990:2011", "name": "Old title"}
        )
        staged = self.stage(KIND_TESTING_METHOD, code="tcvn 9990:2011", name="New title", field_key="x")

        self.assertEqual((staged.record_id, staged.action), (method.id, "update"))
        self.assertEqual(staged.changes, "Name: Old title → New title")
        self.assertIn("Code: tcvn 9990:2011", staged.source_summary)
        self.assertIn("Name: New title", staged.source_summary)

        linked = self.stage(KIND_TESTING_METHOD, code="TCVN 9990:2011", name="Old title", field_key="x")
        self.assertFalse(linked.changes)

    def test_the_match_is_confirmed_or_set_by_hand(self):
        sample = self.env[MODEL_SAMPLE_TYPE].create({"name": "Review Match Sample"})
        staged = self.sample("review match sample")
        self.assertTrue(staged.match_suggested)

        staged.with_user(self.admin).action_confirm_match()
        self.assertEqual((staged.record_id, staged.match_suggested), (sample.id, False))

        other = self.env[MODEL_SAMPLE_TYPE].create({"name": "Another sample"})
        staged.with_user(self.admin).match_ref = other
        self.assertEqual((staged.record_model, staged.record_id), (MODEL_SAMPLE_TYPE, other.id))
        with self.assertRaises(ValidationError):
            staged.with_user(self.admin).match_ref = self.env[MODEL_TESTING_FIELD].create(
                {"code": "ZZRV", "name": "RV"}
            )

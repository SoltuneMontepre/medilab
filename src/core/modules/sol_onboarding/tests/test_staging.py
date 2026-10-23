import hashlib
from datetime import datetime

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_STAGED_RECORD,
)
from odoo.addons.sol_onboarding.constants.onboarding import KIND_CERTIFICATE, KIND_TESTING_METHOD
from odoo.addons.sol_onboarding.constants.xml_ids import SOURCES_GROUP
from odoo.addons.sol_onboarding.services.adapters.base import Fetched, StagedValues
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase

PAGE = "https://lab.example/a"
FETCHED_AT = datetime(2026, 10, 21, 8, 0, 0)


@tagged("post_install", "-at_install")
class TestStaging(OnboardingCase):
    def setUp(self):
        super().setUp()
        self.runs = self.env[MODEL_ONBOARDING_RUN]
        self.run = self.runs.create({"requested_by_id": self.admin.id})
        self.snapshots = self.env[MODEL_ONBOARDING_SNAPSHOT]
        self.records = self.env[MODEL_ONBOARDING_STAGED_RECORD]

    def snapshot_of(self, run=None, body=b"<p>A</p>"):
        return self.snapshots._keep(run or self.run, self.source, Fetched(PAGE, "html", body, FETCHED_AT))

    def method(self, code, name="pH", parent=None):
        return StagedValues(
            KIND_TESTING_METHOD, code, {"code": code, "name": name, "field_key": "chem"}, "vi_VN", parent=parent
        )

    def stage(self, *values, run=None):
        return self.records._stage(self.snapshot_of(run), values)

    def test_a_snapshot_keeps_the_bytes_with_address_time_and_checksum(self):
        snapshot = self.snapshot_of()

        self.assertEqual(bytes(snapshot.attachment_id.raw), b"<p>A</p>")
        self.assertEqual(snapshot.checksum, hashlib.sha256(b"<p>A</p>").hexdigest())
        self.assertEqual((snapshot.url, snapshot.fetched_at, snapshot.content_type), (PAGE, FETCHED_AT, "html"))
        self.assertEqual(
            (snapshot.attachment_id.res_model, snapshot.attachment_id.res_id), (snapshot._name, snapshot.id)
        )

    def test_the_checksum_ignores_key_order(self):
        self.assertEqual(self.records._checksum({"a": "1", "b": "2"}), self.records._checksum({"b": "2", "a": "1"}))

    def test_a_staged_record_starts_to_review_as_a_create(self):
        record = self.stage(self.method("TCVN 1"))

        self.assertEqual((record.state, record.action, record.lang), ("to_review", "create", "vi_VN"))
        self.assertEqual(record.source_values, {"code": "TCVN 1", "name": "pH", "field_key": "chem"})
        self.assertEqual(record.source_id, self.source)

    def test_values_are_cleaned_before_the_checksum(self):
        first = self.stage(self.method("TCVN 1", name="pH"))
        second = self.stage(self.method("TCVN 1", name="  pH\u00a0 "))

        self.assertTrue(first)
        self.assertFalse(second)

    def test_the_same_values_are_not_staged_twice(self):
        first = self.stage(self.method("TCVN 1"))
        self.assertFalse(self.stage(self.method("TCVN 1")))

        first.state = "accepted"
        self.assertFalse(self.stage(self.method("TCVN 1")))

    def test_changed_values_stage_an_update_and_supersede_the_older(self):
        old = self.stage(self.method("TCVN 6492:2011", name="pH"))
        new = self.stage(self.method("TCVN 6492:2011", name="Water quality — pH"))

        self.assertEqual((old.state, new.state), ("superseded", "to_review"))

    def test_changed_values_leave_an_accepted_record_as_it_is(self):
        old = self.stage(self.method("TCVN 1", name="pH"))
        old.state = "accepted"
        new = self.stage(self.method("TCVN 1", name="Water pH"))

        self.assertEqual((old.state, new.state), ("accepted", "to_review"))

    def test_a_rejected_record_is_not_staged_again_while_unchanged(self):
        rejected = self.stage(self.method("TCVN 1"))
        rejected.state = "rejected"

        self.assertFalse(self.stage(self.method("TCVN 1")))
        self.assertTrue(self.stage(self.method("TCVN 1", name="Other")))

    def test_a_child_names_its_parent(self):
        certificate = StagedValues(
            KIND_CERTIFICATE,
            "VILAS 999",
            {"code": "VILAS 999", "issuing_body": "BoA", "valid_from": "", "valid_until": ""},
            "vi_VN",
        )
        staged = self.stage(certificate, self.method("TCVN 1", parent=(KIND_CERTIFICATE, "VILAS 999")))

        self.assertEqual(staged[1].parent_id, staged[0])
        self.assertEqual(staged[0].child_ids, staged[1])

    def test_a_parent_from_an_earlier_run_is_found_when_this_run_has_none(self):
        certificate = StagedValues(KIND_CERTIFICATE, "VILAS 999", {"code": "VILAS 999"}, "vi_VN")
        earlier = self.stage(certificate)
        later = self.runs.create({"requested_by_id": self.admin.id})
        child = self.stage(self.method("TCVN 1", parent=(KIND_CERTIFICATE, "VILAS 999")), run=later)

        self.assertEqual(child.parent_id, earlier)

    def test_a_missing_parent_stays_empty(self):
        child = self.stage(self.method("TCVN 1", parent=(KIND_CERTIFICATE, "VILAS 404")))

        self.assertFalse(child.parent_id)

    def test_each_staged_record_shows_its_page_address_and_time(self):
        record = self.stage(self.method("TCVN 1"))

        shown = record.with_user(self.reader)
        self.assertEqual((shown.page_url, shown.page_fetched_at), (PAGE, FETCHED_AT))

    def test_administrator_cannot_read_the_source_of_a_staged_record(self):
        record = self.stage(self.method("TCVN 1"))

        with self.assertRaises(AccessError):
            record.with_user(self.admin).read(["source_id"])
        self.assertEqual(self.snapshots._fields["source_id"].groups, SOURCES_GROUP)

    def test_a_plain_internal_user_cannot_read_staged_records(self):
        record = self.stage(self.method("TCVN 1"))
        plain = new_test_user(self.env, login="onboarding_plain", groups="base.group_user")

        with self.assertRaises(AccessError):
            self.records.with_user(plain).search([])
        with self.assertRaises(AccessError):
            record.with_user(plain).read(["external_key"])
        self.assertEqual(record.with_user(self.reader).external_key, "TCVN 1")

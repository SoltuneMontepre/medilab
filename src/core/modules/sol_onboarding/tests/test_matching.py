from datetime import date, datetime

from odoo.tests import tagged

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_DEPARTMENT,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_GROUP,
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_PARAMETER,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
    MODEL_UNIT_CATEGORY,
)
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_STAGED_RECORD,
)
from odoo.addons.sol_onboarding.constants.onboarding import (
    KIND_CERTIFICATE,
    KIND_PARAMETER_METHOD,
    KIND_SAMPLE_TYPE,
    KIND_TEST_PARAMETER,
    KIND_TESTING_METHOD,
)
from odoo.addons.sol_onboarding.services.adapters.base import Fetched, StagedValues
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase


@tagged("post_install", "-at_install")
class TestMatching(OnboardingCase):
    def setUp(self):
        super().setUp()
        self.run = self.env[MODEL_ONBOARDING_RUN].create({"requested_by_id": self.admin.id})
        self.records = self.env[MODEL_ONBOARDING_STAGED_RECORD]
        self.field = self.env[MODEL_TESTING_FIELD].create({"code": "ZZMATCH", "name": "Matching field"})
        self.group = self.env[MODEL_PARAMETER_GROUP].create({"name": "Matching group"})

    def stage(self, kind, key=None, **values):
        fetched = Fetched("https://lab.example/a", "html", b"<p>A</p>", datetime(2026, 10, 21, 8, 0, 0))
        snapshot = self.env[MODEL_ONBOARDING_SNAPSHOT]._keep(self.run, self.source, fetched)
        item = StagedValues(kind, key or values.get("code") or values.get("name"), values, "vi_VN")
        return self.records._stage(snapshot, [item])

    def lab_method(self, **values):
        return self.env[MODEL_TESTING_METHOD].create({"field_id": self.field.id, "name": "Matching method", **values})

    def lab_parameter(self, name):
        return self.env[MODEL_TEST_PARAMETER].create(
            {"name": name, "group_ids": [self.group.id], "main_group_id": self.group.id}
        )

    def test_method_code_matches_ignoring_case_and_spaces(self):
        method = self.lab_method(code="TCVN 9876:2011")
        staged = self.stage(KIND_TESTING_METHOD, code="tcvn 9876 : 2011", name=method.name, field_key="x")

        self.assertEqual((staged.record_id, staged.action, staged.match_suggested), (method.id, "link", False))
        self.assertEqual(staged.record_model, MODEL_TESTING_METHOD)

    def test_an_archived_record_still_matches(self):
        method = self.lab_method(code="TCVN 9877:2011")
        method.active = False
        staged = self.stage(KIND_TESTING_METHOD, code="TCVN 9877:2011", name=method.name, field_key="x")

        self.assertEqual(staged.record_id, method.id)

    def test_certificate_matches_by_number(self):
        certificate = self.env[MODEL_ACCREDITATION_CERTIFICATE].create(
            {"code": "VILAS 9001", "issuing_body": "BoA", "valid_from": date(2025, 1, 1), "valid_until": False}
        )
        same = {"code": "vilas9001", "issuing_body": "BoA", "valid_from": "2025-01-01", "valid_until": ""}
        staged = self.stage(KIND_CERTIFICATE, **same)

        self.assertEqual((staged.record_id, staged.action, staged.match_suggested), (certificate.id, "link", False))

        changed = self.stage(KIND_CERTIFICATE, **{**same, "valid_until": "2027-01-01"})
        self.assertEqual((changed.record_id, changed.action), (certificate.id, "update"))

    def test_names_match_as_a_suggestion(self):
        sample = self.env[MODEL_SAMPLE_TYPE].create({"name": "Nước Mặt"})
        staged = self.stage(KIND_SAMPLE_TYPE, name="nước mặt")

        self.assertEqual(
            (staged.record_model, staged.record_id, staged.match_suggested), (MODEL_SAMPLE_TYPE, sample.id, True)
        )
        other = self.stage(KIND_SAMPLE_TYPE, name="Không khí xung quanh")
        self.assertEqual((other.record_id, other.match_suggested, other.action), (0, False, "create"))

    def test_a_match_with_other_values_proposes_an_update(self):
        method = self.lab_method(code="TCVN 9878:2011")
        staged = self.stage(KIND_TESTING_METHOD, code="TCVN 9878:2011", name="A new title", field_key="other")

        self.assertEqual((staged.record_id, staged.action), (method.id, "update"))

    def test_a_different_field_key_alone_is_not_an_update(self):
        method = self.lab_method(code="TCVN 9879:2011")
        staged = self.stage(KIND_TESTING_METHOD, code="TCVN 9879:2011", name=method.name, field_key="other")

        self.assertEqual(staged.action, "link")

    def test_no_match_proposes_to_create(self):
        staged = self.stage(KIND_TESTING_METHOD, code="TCVN 9880:2011", name="New", field_key="x")

        self.assertEqual((staged.record_model, staged.record_id, staged.action), (False, 0, "create"))

    def test_editing_values_matches_again(self):
        method = self.lab_method(code="TCVN 9881:2011")
        staged = self.stage(KIND_TESTING_METHOD, code="TCVN 9881:2010", name=method.name, field_key="x")
        self.assertEqual(staged.record_id, 0)

        staged.edited_values = {"code": "TCVN 9881:2011"}
        self.assertEqual((staged.record_id, staged.action), (method.id, "link"))

        staged.edited_values = {"code": "TCVN 9881:2012"}
        self.assertEqual((staged.record_id, staged.action), (0, "create"))

    def test_a_way_of_testing_matches_its_parameter_and_method_pair(self):
        method = self.lab_method(code="TCVN 9882:2011")
        parameter = self.lab_parameter("Matching parameter")
        category = self.env[MODEL_UNIT_CATEGORY].create({"name": "Matching category"})
        unit = self.env[MODEL_MEASUREMENT_UNIT].create({"name": "mm/mm", "category_id": category.id})
        department = self.env[MODEL_DEPARTMENT].create({"name": "Matching department"})
        pair = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": parameter.id,
                "method_id": method.id,
                "unit_id": unit.id,
                "department_id": department.id,
            }
        )
        staged_parameter = self.stage(KIND_TEST_PARAMETER, name=parameter.name)
        staged_method = self.stage(KIND_TESTING_METHOD, code=method.code, name=method.name, field_key="x")
        self.assertEqual((staged_parameter.record_id, staged_method.record_id), (parameter.id, method.id))

        staged = self.stage(KIND_PARAMETER_METHOD, key="pair", parameter_key=parameter.name, method_key=method.code)
        self.assertEqual(
            (staged.record_model, staged.record_id, staged.action), (MODEL_PARAMETER_METHOD, pair.id, "link")
        )

        pair.active = False
        staged.edited_values = {"method_key": method.code}
        self.assertEqual((staged.record_id, staged.action), (0, "create"))

    def test_a_code_with_a_non_breaking_space_and_full_width_characters_links(self):
        method = self.lab_method(code="TCVN 9883:2011")
        staged = self.stage(KIND_TESTING_METHOD, code="TCVN 9883：２011", name=method.name, field_key="x")

        self.assertEqual(staged.source_values["code"], "TCVN 9883:2011")
        self.assertEqual((staged.record_id, staged.action, staged.match_suggested), (method.id, "link", False))

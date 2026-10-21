from datetime import date, datetime

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged
from odoo.tools import SQL, mute_logger

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
    MODEL_ONBOARDING_ACCEPT,
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SNAPSHOT,
    MODEL_ONBOARDING_STAGED_RECORD,
)
from odoo.addons.sol_onboarding.constants.onboarding import (
    KIND_CERTIFICATE,
    KIND_PARAMETER_METHOD,
    KIND_SAMPLE_TYPE,
    KIND_TEST_PARAMETER,
    KIND_TESTING_FIELD,
    KIND_TESTING_METHOD,
)
from odoo.addons.sol_onboarding.services.adapters.base import Fetched, StagedValues
from odoo.addons.sol_onboarding.tests.onboarding_case import OnboardingCase

FIELD_CODE = "ZZACCFLD"
METHOD_CODE = "TCVN 9701:2011"


@tagged("post_install", "-at_install")
class TestAccepting(OnboardingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.field = cls.env[MODEL_TESTING_FIELD].create({"code": "ZZACCEPT", "name": "Accepting field"})
        cls.group = cls.env[MODEL_PARAMETER_GROUP].create({"name": "Accepting group"})
        category = cls.env[MODEL_UNIT_CATEGORY].create({"name": "Accepting category"})
        cls.unit = cls.env[MODEL_MEASUREMENT_UNIT].create({"name": "zz/accept", "category_id": category.id})
        cls.department = cls.env[MODEL_DEPARTMENT].create({"name": "Accepting department"})
        # Accepts staged records but holds no Laboratory permission.
        cls.editor = new_test_user(
            cls.env,
            login="onboarding_editor",
            groups=(
                "base.group_user,sol_laboratory.group_permission_onboarding_staged_record_read_all,"
                "sol_laboratory.group_permission_onboarding_staged_record_edit_all"
            ),
        )

    def setUp(self):
        super().setUp()
        self.run = self.env[MODEL_ONBOARDING_RUN].create({"requested_by_id": self.admin.id})

    def stage(self, kind, key=None, **values):
        fetched = Fetched("https://lab.example/a", "html", b"<p>A</p>", datetime(2026, 10, 21, 8, 0, 0))
        snapshot = self.env[MODEL_ONBOARDING_SNAPSHOT]._keep(self.run, self.source, fetched)
        item = StagedValues(kind, key or values.get("code") or values["name"], values, "vi_VN")
        return self.env[MODEL_ONBOARDING_STAGED_RECORD]._stage(snapshot, [item])

    def way_of_testing(self):
        """A staged way of testing with its staged parameter and method, and the method's staged testing field, as a
        source gives them: without the parameter's main group, nor the unit and department."""
        field = self.stage(KIND_TESTING_FIELD, code=FIELD_CODE, name="Accepted field")
        method = self.stage(KIND_TESTING_METHOD, code=METHOD_CODE, name="Accepted method", field_key=FIELD_CODE)
        parameter = self.stage(KIND_TEST_PARAMETER, name="Accepted parameter xyz")
        pair = self.stage(
            KIND_PARAMETER_METHOD, "accepted pair", parameter_key=parameter.external_key, method_key=METHOD_CODE
        )
        return pair, parameter, method, field

    def wizard(self, action, **values):
        return self.env[MODEL_ONBOARDING_ACCEPT].with_user(self.admin).with_context(action["context"]).create(values)

    def lab_pairs_for(self, staged):
        return self.env[MODEL_PARAMETER_METHOD].search([("method_id.code", "=", staged.source_values["method_key"])])

    def test_accepting_a_way_of_testing_accepts_its_staged_parameter_and_method_first(self):
        pair, parameter, method, field = self.way_of_testing()

        action = pair.with_user(self.admin).action_accept()

        self.assertEqual(action["res_model"], MODEL_ONBOARDING_ACCEPT)
        self.assertEqual((pair | parameter | method | field).mapped("state"), ["to_review"] * 4)
        wizard = self.wizard(
            action, main_group_id=self.group.id, unit_id=self.unit.id, department_id=self.department.id
        )
        needed = (wizard.main_group_needed, wizard.unit_needed, wizard.department_needed)
        self.assertEqual(needed, (True, True, True))
        self.assertEqual((wizard.field_needed, wizard.code_needed), (False, False))
        self.assertEqual(
            wizard.asked_for.splitlines(),
            [
                "Unit: Parameter Method accepted pair",
                "Department: Parameter Method accepted pair",
                "Main Group: Test Parameter Accepted parameter xyz",
            ],
        )

        self.assertEqual(wizard.action_confirm()["tag"], "display_notification")

        staged = pair | parameter | method | field
        self.assertEqual(staged.mapped("state"), ["accepted"] * 4)
        self.assertEqual(staged.mapped("reviewed_by_id"), self.admin)
        self.assertEqual(parameter.edited_values, {"main_group_id": self.group.id})
        lab_pair = self.env[MODEL_PARAMETER_METHOD].browse(pair.record_id)
        self.assertEqual(lab_pair, self.lab_pairs_for(pair))
        self.assertEqual(lab_pair.parameter_id, self.env[MODEL_TEST_PARAMETER].browse(parameter.record_id))
        self.assertEqual(lab_pair.method_id, self.env[MODEL_TESTING_METHOD].browse(method.record_id))
        self.assertEqual(lab_pair.method_id.field_id, self.env[MODEL_TESTING_FIELD].browse(field.record_id))
        self.assertEqual(lab_pair.method_id.field_id.code, FIELD_CODE)
        self.assertEqual((lab_pair.unit_id, lab_pair.department_id), (self.unit, self.department))
        self.assertEqual(lab_pair.parameter_id.main_group_id, self.group)
        self.assertEqual(lab_pair.parameter_id.group_ids, self.group)

    def test_an_in_house_way_of_testing_asks_for_a_department(self):
        pair, parameter, method, field = self.way_of_testing()
        sample = self.stage(KIND_SAMPLE_TYPE, name="Accepted with the pair xyz")

        refused = (pair | sample).with_user(self.admin).action_accept()

        self.assertEqual(refused["domain"], [("id", "in", pair.ids)])
        self.assertEqual(pair.error, "Test Parameter Accepted parameter xyz needs these values first: Main Group.")
        self.assertEqual((pair | parameter | method | field).mapped("state"), ["to_review"] * 4)
        self.assertEqual(sample.state, "accepted")

        parameter.main_group_id = self.group
        pair.unit_id = self.unit
        action = pair.with_user(self.admin).action_accept()

        self.assertEqual(action["res_model"], MODEL_ONBOARDING_ACCEPT)
        wizard = self.wizard(action)
        self.assertEqual((wizard.department_needed, wizard.unit_needed, wizard.main_group_needed), (True, False, False))
        self.assertEqual(wizard.asked_for, "Department: Parameter Method accepted pair")
        self.assertEqual(pair.state, "to_review")
        self.assertFalse(self.lab_pairs_for(pair))

        pair.department_id = self.department
        # The method, selected after the pair that accepts it first, is not refused for being accepted already.
        action = (pair | method).with_user(self.admin).action_accept()

        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual((pair | parameter | method | field).mapped("state"), ["accepted"] * 4)
        self.assertEqual(self.lab_pairs_for(pair).department_id, self.department)

    def test_a_method_asks_for_the_code_of_its_staged_testing_field(self):
        field = self.stage(KIND_TESTING_FIELD, name="Quorvex zyl")
        method = self.stage(
            KIND_TESTING_METHOD, code="TCVN 9704:2011", name="Quorvex method", field_key=field.external_key
        )

        action = method.with_user(self.admin).action_accept()

        wizard = self.wizard(action, code="ZZACCQUO")
        self.assertEqual((wizard.code_needed, wizard.field_needed), (True, False))
        self.assertEqual(wizard.asked_for, "Code: Testing Field Quorvex zyl")
        wizard.action_confirm()
        self.assertEqual((field | method).mapped("state"), ["accepted"] * 2)
        self.assertEqual(field.edited_values, {"code": "ZZACCQUO"})
        self.assertEqual(self.env[MODEL_TESTING_METHOD].browse(method.record_id).field_id.code, "ZZACCQUO")

    def test_a_refused_accept_keeps_the_record_to_review_with_the_message(self):
        pair, parameter, method, field = self.way_of_testing()
        parameter.main_group_id = self.group
        pair.write({"unit_id": self.unit.id, "department_id": self.department.id})
        # The field's code is taken after it was staged, so its staged match is stale.
        self.env[MODEL_TESTING_FIELD].create({"code": FIELD_CODE, "name": "Taken meanwhile"})

        with mute_logger("odoo.sql_db"):
            action = pair.with_user(self.admin).action_accept()

        self.assertEqual(action["res_model"], MODEL_ONBOARDING_STAGED_RECORD)
        self.assertEqual(action["domain"], [("id", "in", pair.ids)])
        self.assertEqual(pair.error, "The code of a testing field must be unique.")
        self.assertEqual((pair | parameter | method | field).mapped("state"), ["to_review"] * 4)
        self.assertEqual((parameter | method | field).mapped("record_id"), [0, 0, 0])
        self.assertFalse(self.env[MODEL_TEST_PARAMETER].search([("name", "=", "Accepted parameter xyz")]))
        self.assertFalse(self.env[MODEL_TESTING_METHOD].search([("code", "=", METHOD_CODE)]))

    def test_accepting_an_update_changes_only_the_fields_that_differ(self):
        method = self.env[MODEL_TESTING_METHOD].create(
            {"field_id": self.field.id, "code": "TCVN 9702:2011", "name": "Old title"}
        )
        method.active = False
        staged = self.stage(KIND_TESTING_METHOD, code="tcvn 9702:2011", name="New title", field_key="other")
        self.assertEqual((staged.record_id, staged.action), (method.id, "update"))

        staged.with_user(self.admin).action_accept()

        self.assertEqual(
            (staged.state, staged.record_model, staged.record_id), ("accepted", MODEL_TESTING_METHOD, method.id)
        )
        self.assertEqual(method.with_context(lang="vi_VN").name, "New title")
        self.assertEqual(method.with_context(lang="en_US").name, "Old title")
        self.assertEqual((method.code, method.field_id, method.active), ("TCVN 9702:2011", self.field, False))

    def test_a_created_name_is_kept_in_the_staged_language(self):
        staged = self.stage(KIND_TESTING_FIELD, code="ZZACCLANG", name="Lĩnh vực ngôn ngữ")

        staged.with_user(self.admin).with_context(lang="en_US").action_accept()

        field = self.env[MODEL_TESTING_FIELD].browse(staged.record_id)
        field.flush_recordset()
        stored = self.env.execute_query(
            SQL("SELECT name FROM %s WHERE id = %s", SQL.identifier(field._table), field.id)
        )
        self.assertEqual(stored[0][0], {"en_US": "Lĩnh vực ngôn ngữ", "vi_VN": "Lĩnh vực ngôn ngữ"})

    def test_an_update_keeps_a_code_the_source_does_not_give(self):
        field = self.env[MODEL_TESTING_FIELD].create({"code": "ZZACCKEEP", "name": "Accepting Kept Field"})
        staged = self.stage(KIND_TESTING_FIELD, name="accepting kept field")
        staged.with_user(self.admin).action_confirm_match()

        staged.with_user(self.admin).action_accept()

        self.assertEqual((staged.state, staged.record_id), ("accepted", field.id))
        self.assertEqual(field.code, "ZZACCKEEP")

    def test_a_certificate_update_keeps_the_dates_the_staged_record_does_not_give(self):
        certificate = self.env[MODEL_ACCREDITATION_CERTIFICATE].create(
            {
                "code": "VILAS 9701",
                "issuing_body": "BoA",
                "valid_from": date(2025, 1, 1),
                "valid_until": date(2027, 12, 31),
            }
        )
        staged = self.stage(
            KIND_CERTIFICATE, code="VILAS 9701", issuing_body="AOSC", valid_from="01/01/2025", valid_until=""
        )
        self.assertEqual((staged.action, staged.changes), ("update", "Issuing Body: BoA → AOSC"))

        staged.with_user(self.admin).action_accept()

        self.assertEqual(staged.state, "accepted")
        self.assertEqual(
            (certificate.issuing_body, certificate.valid_from, certificate.valid_until),
            ("AOSC", date(2025, 1, 1), date(2027, 12, 31)),
        )

    def test_the_accepted_record_has_the_edited_value(self):
        staged = self.stage(KIND_SAMPLE_TYPE, name="Accepting sample xyz")
        staged.with_user(self.admin).name = "Edited sample xyz"

        staged.with_user(self.admin).action_accept()

        sample = self.env[MODEL_SAMPLE_TYPE].browse(staged.record_id)
        self.assertEqual(sample.with_context(lang="vi_VN").name, "Edited sample xyz")
        self.assertEqual(staged.source_values, {"name": "Accepting sample xyz"})

    def test_an_unconfirmed_name_match_is_refused(self):
        sample = self.env[MODEL_SAMPLE_TYPE].create({"name": "Accepting Match Sample"})
        staged = self.stage(KIND_SAMPLE_TYPE, name="accepting match sample")
        self.assertTrue(staged.match_suggested)

        staged.with_user(self.admin).action_accept()

        self.assertEqual((staged.state, staged.error), ("to_review", "Confirm or clear the suggested match first."))
        staged.with_user(self.admin).action_confirm_match()
        staged.with_user(self.admin).action_accept()
        self.assertEqual((staged.state, staged.record_id, staged.error), ("accepted", sample.id, False))

    def test_without_the_accept_permission_the_api_refuses(self):
        staged = self.stage(KIND_SAMPLE_TYPE, name="Not accepted sample xyz")

        with self.assertRaises(AccessError):
            staged.with_user(self.reader).action_accept()
        self.assertEqual((staged.state, staged.record_id), ("to_review", 0))

    def test_without_the_accept_permission_no_accept_button(self):
        views = [(False, "list"), (False, "form")]
        records = self.env[MODEL_ONBOARDING_STAGED_RECORD]
        for view in records.with_user(self.reader).get_views(views)["views"].values():
            self.assertNotIn("action_accept", view["arch"])
        for view in records.with_user(self.admin).get_views(views)["views"].values():
            self.assertIn("action_accept", view["arch"])

    def test_accepting_needs_the_master_data_permission(self):
        staged = self.stage(KIND_TESTING_METHOD, code="TCVN 9703:2011", name="Not created", field_key="other")
        staged.field_id = self.field

        staged.with_user(self.editor).action_accept()

        self.assertEqual(staged.state, "to_review")
        self.assertIn(MODEL_TESTING_METHOD, staged.error)
        self.assertFalse(self.env[MODEL_TESTING_METHOD].search([("code", "=", "TCVN 9703:2011")]))

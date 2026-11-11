from datetime import date, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo.fields import Command
from odoo.tests import tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TYPE,
    MODEL_SUBCONTRACTOR,
    MODEL_TEST_REQUEST,
    MODEL_TESTING_METHOD,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_id
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestIsAccredited(RequestCase):
    """Lead is accredited with the case's method on Vegetables, so on Cabbage too; Cadmium is tested with the same
    method but is not in the scope."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        SampleType = cls.env[MODEL_SAMPLE_TYPE]
        cls.food = SampleType.create({"name": "Food"})
        cls.vegetables = SampleType.create({"name": "Vegetables", "parent_id": cls.food.id})
        cls.cabbage = SampleType.create({"name": "Cabbage", "parent_id": cls.vegetables.id})
        cls.cabbage_applicability = cls.offer(cls.parameter, cls.cabbage)
        cls.cadmium = cls.create_parameter("Cadmium (Cd)", cls.group)
        cls.cadmium_way = cls.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": cls.cadmium.id, "method_id": cls.method.id, "department_id": cls.department.id}
        )
        cls.offer(cls.cadmium, cls.cabbage, cls.cadmium_way)
        cls.Certificate = cls.env[MODEL_ACCREDITATION_CERTIFICATE]
        cls.today = cls.Certificate._laboratory_today()
        cls.certificate = cls.Certificate.create(
            {
                "code": "VILAS-A",
                "valid_from": cls.today - timedelta(days=10),
                "valid_until": cls.today + timedelta(days=10),
                "scope_line_ids": [cls.scope_line(cls.method, cls.parameter, cls.vegetables)],
            }
        )
        cls.line = cls.certificate.scope_line_ids
        cls.test = cls.sample_test(cls.parameter, cls.cabbage, cls.pair)

    @classmethod
    def sample_test(cls, parameter, sample_type, way):
        request = cls.env[MODEL_TEST_REQUEST].create(
            {
                "customer_id": cls.customer.id,
                "expected_date": "2026-10-20",
                "sample_ids": [
                    Command.create(
                        {
                            "customer_sample_name": f"{parameter.name} on {sample_type.name}",
                            "sample_type_id": sample_type.id,
                            "physical_state": "solid",
                            "test_ids": [Command.create({"parameter_id": parameter.id, "parameter_method_id": way.id})],
                        }
                    )
                ],
            }
        )
        return request.sample_ids.test_ids

    def test_ancestor_sample_type_on_the_line_accredits_the_test(self):
        self.assertTrue(self.test.is_accredited)
        self.assertTrue(self.cabbage_applicability.is_accredited)

    def test_exact_sample_type_on_the_line_accredits_the_test(self):
        self.line.sample_type_ids = [Command.set([persisted_id(self.cabbage)])]
        self.assertTrue(self.test.is_accredited)

    def test_method_match_alone_does_not_accredit_another_parameter(self):
        cadmium = self.sample_test(self.cadmium, self.cabbage, self.cadmium_way)
        self.assertFalse(cadmium.is_accredited)

    def test_method_match_alone_does_not_accredit_another_sample_type(self):
        water = self.sample_test(self.parameter, self.sample_type, self.pair)
        self.assertFalse(water.is_accredited)
        self.assertFalse(self.applicability.is_accredited)

    def test_narrower_type_on_the_line_does_not_accredit_its_parent(self):
        self.line.sample_type_ids = [Command.set([persisted_id(self.cabbage)])]
        self.offer(self.parameter, self.vegetables)
        vegetables = self.sample_test(self.parameter, self.vegetables, self.pair)
        self.assertFalse(vegetables.is_accredited)

    def test_parameter_and_sample_type_must_be_on_the_same_line(self):
        self.line.write(
            {
                "parameter_ids": [Command.set([persisted_id(self.cadmium)])],
                "sample_type_ids": [Command.set([persisted_id(self.vegetables)])],
            }
        )
        self.certificate.scope_line_ids = [self.scope_line(self.method, self.parameter, self.sample_type)]
        self.assertFalse(self.test.is_accredited)
        self.assertTrue(self.sample_test(self.parameter, self.sample_type, self.pair).is_accredited)

    def test_subcontracted_test_is_never_accredited(self):
        subcontracted = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": self.method.id,
                "subcontractor_id": self.env[MODEL_SUBCONTRACTOR].create({"name": "Northern Lab"}).id,
            }
        )
        applicability = self.offer(self.parameter, self.cabbage, subcontracted)
        self.assertFalse(applicability.is_accredited)
        self.test.parameter_method_id = subcontracted
        self.assertFalse(self.test.is_accredited)

    def test_test_without_a_way_is_not_accredited(self):
        self.test.parameter_method_id = False
        self.assertFalse(self.test.is_accredited)

    def test_day_after_valid_until_is_not_accredited(self):
        after = assert_instance(self.certificate.valid_until, date) + timedelta(days=1)
        with (
            freeze_time(f"{after.isoformat()} 10:00:00"),
            patch.object(type(self.env.company), "tz", "Asia/Ho_Chi_Minh"),
        ):
            self.Certificate._recompute_accreditation(self.method)
            self.assertFalse(self.test.is_accredited)
            self.assertFalse(self.cabbage_applicability.is_accredited)

    def test_last_valid_day_ends_at_midnight_in_the_company_time_zone(self):
        last_day = assert_instance(self.certificate.valid_until, date)
        with patch.object(type(self.env.company), "tz", "Asia/Ho_Chi_Minh"):
            # 16:30 UTC is 23:30 in Hanoi, still the last valid day.
            with freeze_time(f"{last_day.isoformat()} 16:30:00"):
                self.Certificate._recompute_accreditation(self.method)
                self.assertTrue(self.test.is_accredited)
            # 17:30 UTC is already the next day in Hanoi, though not yet in UTC.
            with freeze_time(f"{last_day.isoformat()} 17:30:00"):
                self.Certificate._recompute_accreditation(self.method)
                self.assertFalse(self.test.is_accredited)

    def test_first_valid_day_is_accredited(self):
        self.certificate.valid_from = self.today + timedelta(days=5)
        self.assertFalse(self.test.is_accredited)
        on_day = assert_instance(self.certificate.valid_from, date)
        with freeze_time(f"{on_day.isoformat()} 10:00:00"):
            self.Certificate._recompute_accreditation(self.method)
            self.assertTrue(self.test.is_accredited)

    def test_open_ended_certificate_is_accredited(self):
        self.certificate.write({"valid_from": False, "valid_until": False})
        self.assertTrue(self.test.is_accredited)

    def test_future_certificate_is_not_accredited_yet(self):
        self.certificate.write(
            {"valid_from": self.today + timedelta(days=30), "valid_until": self.today + timedelta(days=60)}
        )
        self.assertFalse(self.test.is_accredited)

    def test_overlapping_certificates_keep_accreditation(self):
        self.Certificate.create(
            {
                "code": "VILAS-B",
                "valid_from": self.today - timedelta(days=1),
                "valid_until": self.today + timedelta(days=1),
                "scope_line_ids": [self.scope_line(self.method, self.parameter, self.cabbage)],
            }
        )
        self.certificate.valid_until = self.today - timedelta(days=1)
        self.assertTrue(self.test.is_accredited)

    def test_removing_the_line_clears_accreditation(self):
        self.line.unlink()
        self.assertFalse(self.test.is_accredited)
        self.assertFalse(self.cabbage_applicability.is_accredited)

    def test_archiving_certificate_clears_accreditation_and_keeps_its_lines(self):
        self.certificate.active = False
        self.assertFalse(self.test.is_accredited)
        self.assertEqual(self.certificate.scope_line_ids, self.line)

    def test_restoring_certificate_restores_accreditation(self):
        self.certificate.active = False
        self.certificate.active = True
        self.assertTrue(self.test.is_accredited)

    def test_deleting_certificate_clears_accreditation(self):
        self.certificate.unlink()
        self.assertFalse(self.test.is_accredited)

    def test_changing_the_way_recomputes(self):
        other = self.env[MODEL_TESTING_METHOD].create(
            {"code": "OTHER-1", "name": "Other", "field_id": self.testing_field.id}
        )
        self.pair.method_id = other
        self.assertFalse(self.test.is_accredited)
        self.assertFalse(self.cabbage_applicability.is_accredited)

    def test_changing_the_sample_type_recomputes(self):
        self.offer(self.parameter, self.food)
        self.test.sample_id.sample_type_id = self.food
        self.assertFalse(self.test.is_accredited)

    def test_moving_the_sample_type_out_of_the_scope_recomputes(self):
        self.cabbage.parent_id = self.food
        self.assertFalse(self.test.is_accredited)
        self.assertFalse(self.cabbage_applicability.is_accredited)

    def test_approved_test_keeps_its_mark_after_the_certificate_expires(self):
        self.test.status = "approved"
        self.certificate.valid_until = self.today - timedelta(days=1)
        self.assertTrue(self.test.is_accredited)
        self.assertFalse(self.cabbage_applicability.is_accredited)

    def test_approving_works_the_mark_out_on_that_day(self):
        self.certificate.write({"valid_until": self.today + timedelta(days=1)})
        after = self.today + timedelta(days=2)
        with freeze_time(f"{after.isoformat()} 10:00:00"):
            self.test.status = "approved"
        self.assertFalse(self.test.is_accredited)

    def test_cancelled_test_keeps_its_mark(self):
        self.test.status = "cancelled"
        self.line.unlink()
        self.assertTrue(self.test.is_accredited)

    def test_certificate_edit_does_not_recompute_tests_of_other_methods(self):
        other_method = self.env[MODEL_TESTING_METHOD].create(
            {"code": "OTHER-1", "name": "Other", "field_id": self.testing_field.id}
        )
        other_way = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": self.parameter.id, "method_id": other_method.id, "department_id": self.department.id}
        )
        self.offer(self.parameter, self.food, other_way)
        other = self.sample_test(self.parameter, self.food, other_way)
        # A stale mark on a test of another method stays until its own method is worked out again.
        other.flush_recordset()
        self.env.cr.execute("UPDATE medilab_sample_test SET is_accredited = TRUE WHERE id = %s", [other.id])
        other.invalidate_recordset(["is_accredited"])
        self.certificate.valid_until = self.today
        self.assertTrue(other.is_accredited)

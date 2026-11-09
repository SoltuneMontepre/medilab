from datetime import timedelta

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import MODEL_REGULATION, MODEL_SAMPLE, MODEL_SAMPLE_TYPE


@tagged("post_install", "-at_install")
class TestOrderSampleRegulation(OrderCase):
    """A regulation on the order's sample type, with no fixed dates."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = cls.env[MODEL_SAMPLE]._company_today()
        cls.regulation = cls.env[MODEL_REGULATION].create(
            {"code": "QCVN 6-1:2010/BYT", "name": "Bottled drinking waters", "sample_type_ids": cls.sample_type.ids}
        )

    def test_a_sample_on_an_order_takes_only_a_regulation_it_can_choose_today(self):
        sample = self.make_quotable_order().sample_ids
        expired = self.regulation.copy({"code": "QCVN 01:2009/BYT", "valid_until": self.today - timedelta(days=1)})
        elsewhere = self.regulation.copy(
            {"code": "QCVN 08:2023/BTNMT", "sample_type_ids": self.env[MODEL_SAMPLE_TYPE].create({"name": "River"}).ids}
        )

        for regulation in (expired, elsewhere):
            with self.subTest(regulation.code), self.assertRaises(ValidationError):
                sample.regulation_id = regulation
        sample.regulation_id = self.regulation
        self.assertEqual(sample.regulation_id, self.regulation)

    def test_an_accepted_regulation_that_expires_before_confirmation_is_kept_with_a_notice(self):
        order = self.make_quotable_order()
        order.sample_ids.regulation_id = self.regulation
        order.with_user(self.sales).action_send_quotation()
        self.regulation.valid_until = self.today - timedelta(days=1)

        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()

        self.assertIn("no longer in force", order.sample_ids.regulation_notice or "")
        self.assertEqual(order.test_request_id.sample_ids.regulation_id, self.regulation)

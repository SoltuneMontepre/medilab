from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .support_case import SupportCase
from odoo.addons.sol_commerce.constants.models import MODEL_RATING, MODEL_SALE_ORDER


@tagged("post_install", "-at_install")
class TestOrderFeedback(SupportCase):
    def completed_order(self):
        return self.make_order([(self.lead_product, 1)], status="completed", user_id=self.sales.id)

    def test_feedback_on_a_completed_order_is_a_rating_with_a_message(self):
        order = self.completed_order()
        self.assertTrue(order.can_give_feedback())

        rating = order.with_user(self.portal).action_give_feedback("4", " Fast results. ")

        self.assertEqual((rating.rating, rating.feedback, rating.consumed), (4, "Fast results.", True))
        self.assertEqual((rating.partner_id, rating.rated_partner_id), (self.contact, self.sales.partner_id))
        self.assertEqual((rating.res_model, rating.res_id), (MODEL_SALE_ORDER, order.id))
        self.assertEqual((order.feedback_rating, order.feedback_comment), (4, "Fast results."))
        self.assertEqual(order.with_user(self.sales).feedback_rating, 4)
        self.assertEqual(len(order.message_ids.filtered("rating_ids")), 1)
        self.assertFalse(order.can_give_feedback())

    def test_feedback_only_once_per_order(self):
        order = self.completed_order()
        order.with_user(self.portal).action_give_feedback(5)

        with self.assertRaises(UserError):
            order.with_user(self.portal).action_give_feedback(3, "Changed my mind")
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.env[MODEL_RATING].create(
                {
                    "partner_id": self.contact.id,
                    "res_model_id": self.env["ir.model"]._get_id(MODEL_SALE_ORDER),
                    "res_id": order.id,
                    "rating": 2,
                    "consumed": True,
                }
            )
            self.env.flush_all()

        self.assertEqual(order.feedback_rating, 5)

    def test_feedback_only_on_a_completed_order(self):
        confirmed = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)

        self.assertFalse(confirmed.can_give_feedback())
        with self.assertRaises(UserError):
            confirmed.with_user(self.portal).action_give_feedback(5)

    def test_rating_must_be_from_one_to_five(self):
        order = self.completed_order()

        for rate in (0, 6, "abc", None):
            with self.subTest(rate=rate), self.assertRaises(UserError):
                order.with_user(self.portal).action_give_feedback(rate)
        self.assertFalse(order.feedback_rating)

    def test_another_customer_never_sees_or_gives_the_feedback(self):
        order = self.completed_order()
        rating = order.with_user(self.portal).action_give_feedback(5, "Great")

        with self.assertRaises(AccessError):
            order.with_user(self.other_portal).action_give_feedback(1, "Bad")
        with self.assertRaises(AccessError):
            rating.with_user(self.other_portal).read(["rating"])
        with self.assertRaises(AccessError):
            rating.with_user(self.portal).read(["rating"])
        self.assertEqual(
            self.env[MODEL_RATING]
            .with_user(self.sales)
            .search([("res_model", "=", MODEL_SALE_ORDER), ("res_id", "=", order.id)]),
            rating,
        )

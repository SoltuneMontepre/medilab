from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .support_case import SupportCase
from odoo.addons.sol_commerce.constants.models import MODEL_RATING, MODEL_SALE_ORDER

READ_FIELDS = ["rating", "feedback"]


@tagged("post_install", "-at_install")
class TestFeedbackAccess(SupportCase):
    """Who reads, changes or creates the feedback of an order, through the ORM as a JSON-RPC call reaches it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tester = cls.env["res.users"].create({"name": "Vo Van Thu", "login": "lab.tester"})
        cls.admin = cls.env.ref("base.user_admin")

    def setUp(self):
        super().setUp()
        self.order = self.make_order([(self.lead_product, 1)], status="completed", user_id=self.sales.id)
        self.feedback = self.order.with_user(self.portal).action_give_feedback(4, "Fast results.")
        self.ratings = self.env[MODEL_RATING]

    def known_id(self, user):
        return self.ratings.with_user(user).browse(self.feedback.id)

    def assert_cannot_read(self, user):
        """A user without any rating access is refused; one with it finds nothing."""
        found = [("id", "=", self.feedback.id)]
        ratings = self.ratings.with_user(user)
        if ratings.has_access("read"):
            self.assertFalse(ratings.search(found))
            self.assertFalse(ratings.search_read(found, READ_FIELDS))
        else:
            with self.assertRaises(AccessError):
                ratings.search_read(found, READ_FIELDS)
        with self.assertRaises(AccessError):
            self.known_id(user).read(READ_FIELDS)

    def test_sales_and_management_read_the_feedback_of_orders_they_can_read(self):
        for user in (self.sales, self.head, self.admin):
            with self.subTest(user=user.login):
                self.assertEqual(self.known_id(user).read(READ_FIELDS)[0]["rating"], 4)
                self.assertEqual(self.ratings.with_user(user).search([("id", "=", self.feedback.id)]), self.feedback)

    def test_users_who_cannot_read_the_order_never_read_its_feedback(self):
        for user in (self.tester, self.other_sales, self.portal, self.other_portal):
            with self.subTest(user=user.login):
                self.assert_cannot_read(user)

    def test_nobody_changes_feedback_once_given(self):
        for user in (self.sales, self.head, self.admin, self.tester, self.other_sales, self.portal):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.known_id(user).write({"rating": 1, "feedback": "Changed"})
        self.assertEqual((self.feedback.rating, self.feedback.feedback), (4, "Fast results."))

    def test_only_administrators_delete_feedback(self):
        for user in (self.sales, self.head, self.tester, self.other_sales, self.portal):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.known_id(user).unlink()

        self.known_id(self.admin).unlink()

        self.assertFalse(self.feedback.exists())

    def test_staff_cannot_create_feedback_for_a_customer(self):
        other = self.make_order([(self.lead_product, 1)], status="completed", user_id=self.sales.id)
        values = {
            "res_model_id": self.env["ir.model"]._get_id(MODEL_SALE_ORDER),
            "res_id": other.id,
            "partner_id": self.contact.id,
            "rating": 1,
            "consumed": True,
        }
        for user in (self.sales, self.head, self.tester):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.ratings.with_user(user).create(values)
        with self.assertRaises(AccessError):
            other.with_user(self.sales).message_post(body="Bad", rating_value=1)

        self.assertTrue(other.can_give_feedback())

    def test_the_order_fields_follow_the_order_access(self):
        self.assertEqual(self.order.with_user(self.sales).feedback_rating, 4)
        self.assertEqual(self.order.with_user(self.portal).feedback_rating, 4)
        for user in (self.tester, self.other_portal):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.order.with_user(user).read(["feedback_rating", "feedback_comment"])

    def test_other_ratings_keep_odoo_access(self):
        partner_rating = self.ratings.with_user(self.tester).create(
            {
                "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": self.contact.id,
                "partner_id": self.contact.id,
                "rating": 3,
            }
        )
        partner_rating.write({"rating": 5})

        self.assertEqual(partner_rating.with_user(self.tester).read(["rating"])[0]["rating"], 5)

    def test_rating_invitations_do_not_block_the_one_feedback(self):
        order = self.make_order([(self.lead_product, 1)], status="completed", user_id=self.sales.id)
        order._rating_get_access_token(self.contact)
        order._rating_get_access_token(self.customer)

        order.with_user(self.portal).action_give_feedback(5)

        consumed = order.sudo().rating_ids.filtered("consumed")
        self.assertEqual(len(consumed), 1)
        self.assertEqual(consumed.rating, 5)

    def test_a_second_consumed_rating_on_an_order_is_refused(self):
        values = {
            "res_model_id": self.env["ir.model"]._get_id(MODEL_SALE_ORDER),
            "res_id": self.order.id,
            "partner_id": self.contact.id,
            "rating": 2,
            "consumed": True,
        }
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.ratings.sudo().create(values)
            self.env.flush_all()

    def test_a_feedback_given_meanwhile_is_reported_not_crashed(self):
        order = self.make_order([(self.lead_product, 1)], status="completed", user_id=self.sales.id)
        order.with_user(self.portal).action_give_feedback(5)
        model = type(order)
        no_feedback = model._feedback
        model._feedback = lambda record: record.env[MODEL_RATING]
        try:
            with self.assertRaises(UserError):
                order.with_user(self.portal).action_give_feedback(1)
        finally:
            model._feedback = no_feedback

        self.assertEqual(order.feedback_rating, 5)

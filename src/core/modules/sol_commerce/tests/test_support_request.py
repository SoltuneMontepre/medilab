from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .support_case import SupportCase
from odoo.addons.sol_commerce.constants.models import MODEL_SUPPORT_REQUEST
from odoo.addons.sol_commerce.constants.xml_ids import SUPPORT_READ_ACCESS
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER


@tagged("post_install", "-at_install")
class TestSupportRequest(SupportCase):
    def test_request_about_an_order_goes_to_its_salesperson_as_a_task(self):
        order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)

        request = self.open_request(order=order)

        self.assertEqual(
            (request.status, request.handled_by_id, request.opened_by_id), ("open", self.sales, self.portal)
        )
        self.assertTrue(request.code.startswith("HT."))
        self.assertEqual(request.customer_id, self.customer_record)
        self.assertIn(request, order.with_user(self.sales).support_request_ids)
        task = self.tasks_of(request)
        self.assertEqual(
            (task.assignee_id, task.status, task.type_id.code), (self.sales_person, "assigned", "support_request")
        )
        self.assertIn(task, self.todo(self.sales))
        self.assertNotIn(task, self.todo(self.other_sales))
        self.assertIn(self.contact, request.message_partner_ids)
        self.assertIn(self.sales.partner_id, request.message_partner_ids)
        self.assertEqual(len(request.message_ids.filtered(lambda message: "Please help." in message.body)), 1)

    def test_request_about_no_order_waits_until_a_salesperson_takes_it(self):
        request = self.open_request(subject="Export certificate")
        requests = self.env[MODEL_SUPPORT_REQUEST]

        self.assertFalse(request.handled_by_id)
        self.assertFalse(self.tasks_of(request))
        self.assertIn(request, requests.with_user(self.sales).search([]))
        self.assertIn(request, requests.with_user(self.other_sales).search([]))

        request.with_user(self.other_sales).action_take()

        self.assertEqual(request.handled_by_id, self.other_sales)
        self.assertIn(self.tasks_of(request), self.todo(self.other_sales))
        self.assertNotIn(request, requests.with_user(self.sales).search([]))
        self.assertIn(request, requests.with_user(self.head).search([]))
        with self.assertRaises(UserError):
            request.with_user(self.head).action_take()

    def test_reply_from_sales_answers_the_request_and_notifies_the_customer(self):
        order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)
        request = self.open_request(order=order)

        message = self.write_on(request, self.sales, "The results are released today.")

        self.assertEqual(request.status, "answered")
        self.assertIn(self.contact, message.notified_partner_ids)
        self.assertEqual(self.tasks_of(request).status, "done")

    def test_internal_note_does_not_answer_the_request(self):
        request = self.open_request()

        self.write_on(request, self.sales, "Checking with the laboratory.", subtype="mail.mt_note")

        self.assertEqual(request.status, "open")
        self.assertFalse(request.handled_by_id)

    def test_reply_to_an_untaken_request_takes_it(self):
        request = self.open_request()

        self.write_on(request, self.other_sales, "We can issue one.")

        self.assertEqual((request.status, request.handled_by_id), ("answered", self.other_sales))
        self.assertIn(self.other_sales.partner_id, request.message_partner_ids)

    def test_customer_message_on_an_answered_request_opens_it_again(self):
        order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)
        request = self.open_request(order=order)
        self.write_on(request, self.sales, "Released today.")

        self.write_on(request, self.portal, "I cannot download them.")

        self.assertEqual(request.status, "open")
        tasks = self.tasks_of(request)
        self.assertEqual(sorted(tasks.mapped("status")), ["assigned", "done"])
        self.assertIn(tasks.filtered(lambda task: task.status == "assigned"), self.todo(self.sales))

    def test_customer_e_mail_reply_opens_an_answered_request_again(self):
        order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)
        request = self.open_request(order=order)
        self.write_on(request, self.sales, "Released today.")

        request.message_post(
            body="The link does not work.",
            author_id=self.contact.id,
            message_type="email",
            subtype_xmlid="mail.mt_comment",
        )

        self.assertEqual(request.status, "open")

    def test_upgrade_scopes_the_generated_access_again(self):
        access = self.env.ref(SUPPORT_READ_ACCESS)
        request = self.open_request()
        request.with_user(self.other_sales).action_take()
        access.domain = "[(1, '=', 1)]"
        self.assertIn(request, self.env[MODEL_SUPPORT_REQUEST].with_user(self.sales).search([]))

        self.env[MODEL_SUPPORT_REQUEST]._scope_permission_accesses()

        self.assertNotIn(request, self.env[MODEL_SUPPORT_REQUEST].with_user(self.sales).search([]))

    def test_sales_closes_the_request_and_the_customer_cannot_write_on_it(self):
        order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)
        request = self.open_request(order=order)

        request.with_user(self.sales).action_close()

        self.assertEqual(request.status, "closed")
        self.assertTrue(request.closed_at)
        self.assertEqual(self.tasks_of(request).status, "done")
        with self.assertRaises(UserError):
            self.write_on(request, self.portal, "One more thing.")
        with self.assertRaises(UserError):
            request.with_user(self.portal).message_post(body="By another type.", message_type="email")
        with self.assertRaises(UserError):
            request.with_user(self.sales).action_close()
        with self.assertRaises(UserError):
            request.with_user(self.other_sales).action_take()

    def test_a_closed_request_cannot_be_taken(self):
        request = self.open_request()
        request.with_user(self.head).action_close()

        with self.assertRaises(UserError):
            request.with_user(self.sales).action_take()
        self.assertFalse(request.handled_by_id)

    def test_the_e_mail_link_opens_the_portal_page(self):
        request = self.open_request()

        self.assertEqual(request.access_url, f"/support/{request.id}")
        self.assertIn(f"/support/{request.id}?access_token=", request.get_portal_url())

    def test_sales_finds_support_and_feedback_in_the_sales_app(self):
        support_menus = {"sol_commerce.menu_support_request", "sol_commerce.menu_order_feedback"}
        staff = self.env["res.users"].create({"name": "Vo Van Lab", "login": "lab.staff"})

        def menus(user):
            loaded = self.env["ir.ui.menu"].with_user(user).load_menus(False)
            return {menu.get("xmlid") for menu in loaded.values() if isinstance(menu, dict)}

        self.assertLessEqual({"sale.sale_menu_root", *support_menus}, menus(self.sales))
        self.assertFalse(support_menus & menus(staff))

    def test_customer_cannot_take_or_close(self):
        request = self.open_request()

        with self.assertRaises(AccessError):
            request.with_user(self.portal).action_take()
        with self.assertRaises(AccessError):
            request.with_user(self.portal).action_close()

    def test_another_customer_never_sees_the_request(self):
        request = self.open_request()
        requests = self.env[MODEL_SUPPORT_REQUEST]

        self.assertEqual(requests.with_user(self.portal).search([]), request)
        self.assertFalse(requests.with_user(self.other_portal).search([]))
        self.assertFalse(requests.with_user(self.other_portal).portal_request(request.id))
        self.assertEqual(requests.with_user(self.portal).portal_requests(), request)
        with self.assertRaises(AccessError):
            request.with_user(self.other_portal).read(["subject"])

    def test_request_needs_a_subject_a_question_and_the_customers_own_order(self):
        order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)

        with self.assertRaises(UserError):
            self.open_request(subject="  ", order=order)
        with self.assertRaises(UserError):
            self.open_request(body="  ")
        with self.assertRaises(UserError):
            self.open_request(order=order, user=self.other_portal)
        with self.assertRaises(UserError):
            self.env[MODEL_SUPPORT_REQUEST].with_user(self.portal).portal_open("Forged order", "1 OR 1=1", "Help")
        with self.assertRaises(ValidationError):
            self.env[MODEL_SUPPORT_REQUEST].with_user(self.sales).create(
                {"customer_id": self.customer_record.id, "subject": "Wrong order", "order_id": order.id}
            ).write({"customer_id": self.env[MODEL_CUSTOMER].search([("partner_id", "=", self.other_customer.id)]).id})

    def test_portal_user_without_a_customer_profile_is_refused(self):
        partner = self.env["res.partner"].create({"name": "Nguyen Van Moi", "email": "moi@example.com"})
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Nguyen Van Moi",
                    "login": "portal.moi",
                    "partner_id": partner.id,
                    "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
                }
            )
        )

        with self.assertRaises(UserError):
            self.open_request(user=user)

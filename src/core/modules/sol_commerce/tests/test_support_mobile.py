from odoo.tests import tagged

from .support_case import SupportCase
from odoo.addons.sol_commerce.constants.support import SUPPORT_ANSWERED, SUPPORT_CLOSED, SUPPORT_OPEN
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    IDEMPOTENCY_CONFLICT,
    INVALID_REQUEST,
    NOT_FOUND,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.medilab_mobile import ACTION_REFUSED, ALREADY_TAKEN
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON
from odoo.addons.sol_laboratory.tests.laboratory_api_case import LaboratoryApiCase
from odoo.addons.sol_laboratory.tests.laboratory_files_case import PASSWORD

ANSWER = "Your results are ready on Friday."


@tagged("post_install", "-at_install")
class TestSupportMobile(LaboratoryApiCase, SupportCase):
    """Support requests on Medilab Mobile: a customer's question nobody has taken yet, handled by two salespeople and
    the Head of Sales, and looked for by a tester who handles no support."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tester_person = cls.env[MODEL_PERSON].create({"name": "Vo Van Thanh", "login": "tester.support"})
        for person in (cls.sales_person, cls.other_person, cls.head_person, cls.tester_person):
            person.user_id.password = PASSWORD

    def setUp(self):
        super().setUp()
        self.keys = {}
        self.request = self.open_request()

    def on_phone(self, person, method, path, body=None, headers=None):
        if person not in self.keys:
            self.keys[person] = self.signed_in_key(
                person.user_id, f"phone-{person.id}", name="Galaxy A55", platform="android"
            )
        return self.api(method, path, body, key=self.keys[person], headers=headers)

    def answered(self, response) -> dict:
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def listed(self, person, name):
        return [
            request["id"]
            for request in self.answered(self.on_phone(person, "GET", f"/support-requests?list={name}"))["requests"]
        ]

    def answer(self, person, request=None, body=ANSWER, key=None):
        headers = {"Idempotency-Key": key} if key else None
        path = f"/support-requests/{(request or self.request).id}/answer"
        return self.on_phone(person, "POST", path, {"body": body}, headers=headers)

    def test_the_phone_shows_support_requests_only_to_those_who_handle_them(self):
        for person, may in ((self.sales_person, True), (self.head_person, True), (self.tester_person, False)):
            with self.subTest(person=person.name):
                can = self.answered(self.on_phone(person, "GET", "/me"))["can"]
                self.assertIs(can["take_support_requests"], may)
        self.assertApiRefused(
            NOT_FOUND, self.on_phone(self.tester_person, "GET", f"/support-requests/{self.request.id}")
        )
        self.assertApiRefused(
            NOT_FOUND, self.on_phone(self.tester_person, "POST", f"/support-requests/{self.request.id}/take")
        )

    def test_a_salesperson_takes_a_waiting_request_into_their_own_list(self):
        self.assertIn(self.request.id, self.listed(self.sales_person, "waiting"))
        self.assertNotIn(self.request.id, self.listed(self.sales_person, "mine"))

        taken = self.answered(self.on_phone(self.sales_person, "POST", f"/support-requests/{self.request.id}/take"))
        again = self.answered(self.on_phone(self.sales_person, "POST", f"/support-requests/{self.request.id}/take"))

        self.assertEqual(self.request.handled_by_id, self.sales)
        self.assertEqual(
            (taken["handled_by"], taken["actions"]), (self.sales_person.name, {"take": False, "answer": True})
        )
        self.assertEqual(again["handled_by"], self.sales_person.name)
        self.assertEqual(self.listed(self.sales_person, "mine"), [self.request.id])
        self.assertNotIn(self.request.id, self.listed(self.sales_person, "waiting"))
        self.assertEqual(self.todo(self.sales).document_id, self.request.id)

    def test_a_request_someone_else_took_first_is_already_taken_and_no_longer_shown(self):
        self.answered(self.on_phone(self.other_person, "POST", f"/support-requests/{self.request.id}/take"))

        self.assertApiRefused(
            ALREADY_TAKEN, self.on_phone(self.sales_person, "POST", f"/support-requests/{self.request.id}/take")
        )
        self.assertApiRefused(
            NOT_FOUND, self.on_phone(self.sales_person, "GET", f"/support-requests/{self.request.id}")
        )
        self.assertApiRefused(NOT_FOUND, self.answer(self.sales_person))
        self.assertEqual(self.request.handled_by_id, self.other_person.user_id)

    def test_an_answer_from_the_phone_sets_the_request_answered_and_notifies_the_customer(self):
        request = self.answered(self.answer(self.sales_person))

        message = self.request.message_ids.filtered(lambda each: each.author_id == self.sales.partner_id)
        self.assertEqual((self.request.status, self.request.handled_by_id), (SUPPORT_ANSWERED, self.sales))
        self.assertIn(self.contact, message.notification_ids.res_partner_id)
        self.assertFalse(self.todo(self.sales))
        self.assertEqual(request["status"], SUPPORT_ANSWERED)
        self.assertEqual(
            [(each["body"], each["from_customer"]) for each in request["messages"]],
            [("Please help.", True), (ANSWER, False)],
        )

    def test_the_requests_the_person_handles_list_the_open_ones_first(self):
        answered = self.open_request("Invoice address")
        self.answered(self.on_phone(self.sales_person, "POST", f"/support-requests/{self.request.id}/take"))
        self.answered(self.answer(self.sales_person, answered))

        self.assertEqual(self.listed(self.sales_person, "mine"), [self.request.id, answered.id])

    def test_an_answer_sent_again_with_its_key_is_posted_once(self):
        self.answered(self.answer(self.sales_person, key="answer-1"))
        self.answered(self.answer(self.sales_person, key="answer-1"))
        other = self.open_request("Invoice address")

        self.assertApiRefused(IDEMPOTENCY_CONFLICT, self.answer(self.sales_person, other, key="answer-1"))
        self.assertEqual(
            len(self.request.message_ids.filtered(lambda each: each.author_id == self.sales.partner_id)), 1
        )
        self.assertEqual(other.status, SUPPORT_OPEN)

    def test_a_closed_request_is_neither_taken_nor_answered(self):
        self.request.sudo().action_close()

        self.assertFalse(
            self.answered(self.on_phone(self.head_person, "GET", f"/support-requests/{self.request.id}"))["actions"][
                "answer"
            ]
        )
        self.assertApiRefused(
            ACTION_REFUSED, self.on_phone(self.sales_person, "POST", f"/support-requests/{self.request.id}/take")
        )
        self.assertApiRefused(ACTION_REFUSED, self.answer(self.head_person))
        self.assertEqual(self.request.status, SUPPORT_CLOSED)

    def test_an_empty_answer_or_one_without_the_right_to_edit_is_refused(self):
        self.assertApiRefused(INVALID_REQUEST, self.answer(self.sales_person, body="  "))
        self.sales_person.permission_ids = self.sales_person.permission_ids.filtered(
            lambda permission: permission.code != "support.request.edit.all"
        )

        self.assertApiRefused(PERMISSION_DENIED, self.answer(self.sales_person))
        self.assertEqual(self.request.status, SUPPORT_OPEN)

import re
from secrets import token_urlsafe

from odoo.tests import HttpCase, tagged

from .dispatch_case import DispatchCase


@tagged("post_install", "-at_install")
class TestDispatchPortal(HttpCase, DispatchCase):
    def test_a_subcontractor_user_sees_their_dispatch_by_lab_code_and_never_the_customer(self):
        dispatch = self.send_dispatch(self.outsource())
        self.sign_in(self.northern_user)

        page = self.url_open(f"/my/dispatches/{dispatch.id}")

        self.assertEqual(page.status_code, 200)
        self.assertIn(self.sample.code, page.text)
        self.assertIn(self.parameter.name, page.text)
        self.assertNotIn(self.customer.name, page.text)
        self.assertNotIn(self.sample.customer_sample_name, page.text)

    def test_a_subcontractor_user_cannot_open_another_subcontractor_dispatch(self):
        dispatch = self.send_dispatch(self.outsource())
        self.sign_in(self.southern_user)

        page = self.url_open(f"/my/dispatches/{dispatch.id}")

        self.assertNotIn(self.sample.code, page.text)
        self.assertTrue(page.url.endswith("/my/dispatches"))

    def test_a_subcontractor_user_sees_their_rejected_result_and_the_reason_beside_the_field(self):
        dispatch = self.send_dispatch(self.outsource())
        result = self.enter_on_portal(dispatch, "7")
        self.send_portal_result(result)
        self.as_person(result, self.head).action_reject("The blank was contaminated; measure it again.")
        self.sign_in(self.northern_user)

        page = self.url_open(f"/my/dispatches/{dispatch.id}")

        self.assertIn("Rejected: 7", page.text)
        self.assertIn("The blank was contaminated; measure it again.", page.text)
        self.assertIn('name="value"', page.text)

    def test_a_refused_result_shows_the_system_message_and_never_text_from_the_address(self):
        dispatch = self.send_dispatch(self.outsource())
        self.sign_in(self.northern_user)

        forged = self.url_open(f"/my/dispatches/{dispatch.id}?error=Send+your+results+to+someone+else")
        refused = self.enter_through_the_page(dispatch, "-0.5")

        self.assertNotIn("Send your results to someone else", forged.text)
        self.assertNotIn("error=", refused.url)
        self.assertIn("cannot be negative", refused.text)
        self.assertFalse(self.test.result_ids)
        self.assertNotIn("cannot be negative", self.url_open(f"/my/dispatches/{dispatch.id}").text)

    def enter_through_the_page(self, dispatch, value):
        page = self.url_open(f"/my/dispatches/{dispatch.id}").text
        token = re.search(r'name="csrf_token" value="([^"]+)"', page)
        self.assertTrue(token)
        return self.url_open(
            f"/my/dispatches/{dispatch.id}/results",
            data={"csrf_token": token and token.group(1), "sample_test_id": str(self.test.id), "value": value},
        )

    def sign_in(self, user):
        # A throwaway password, so no credential is written in the code.
        secret = token_urlsafe(16)
        user.password = secret
        self.authenticate(user.login, secret)

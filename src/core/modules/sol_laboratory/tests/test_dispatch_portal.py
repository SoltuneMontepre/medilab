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

    def sign_in(self, user):
        # A throwaway password, so no credential is written in the code.
        secret = token_urlsafe(16)
        user.password = secret
        self.authenticate(user.login, secret)

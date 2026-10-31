from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_api_case import BROWSER_NAVIGATION, LaboratoryApiCase
from .laboratory_files_case import PASSWORD
from odoo.addons.sol_laboratory.constants.laboratory_files import INVALID_KEY, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE, MODEL_RES_USERS_APIKEYS
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services.record_id import persisted_id


@tagged("post_install", "-at_install")
class TestLaboratoryApiKeys(LaboratoryApiCase):
    """Every route of a computer refuses a call that does not come with the key of a signed-in computer of the person."""

    def setUp(self):
        super().setUp()
        self.key = self.signed_in_key(self.tester, "first-installation")
        self.other_key = self.signed_in_key(self.tester, "second-installation", name="AAS-PC")
        devices = self.env[MODEL_LABORATORY_DEVICE].search([("user_id", "=", self.tester.id)])
        self.first = devices.filtered(lambda device: device.client_uid == "first-installation")
        self.second = devices - self.first

    def calls(self):
        """A call of each route of a computer, by its operation."""
        return {
            "listDevices": ("GET", "/devices"),
            "signOut": ("POST", "/sign-out"),
            "revokeDevice": ("POST", f"/devices/{self.second.id}/revoke"),
        }

    def assertEveryRouteRefuses(self, code, key=None, headers=None):
        for operation, (method, path) in self.calls().items():
            with self.subTest(operation=operation):
                self.assertApiRefused(code, self.api(method, path, key=key, headers=headers))

    def test_a_call_without_a_key_is_refused(self):
        self.assertEveryRouteRefuses(INVALID_KEY)

    def test_a_signed_in_browser_session_never_takes_the_place_of_a_key(self):
        self.authenticate(self.tester.login, PASSWORD)

        self.assertEveryRouteRefuses(INVALID_KEY, headers=BROWSER_NAVIGATION)
        self.assertEqual(self.second.status, "signed_in")

    def test_a_key_of_another_scope_is_refused(self):
        rpc_key = self.env[MODEL_RES_USERS_APIKEYS].with_user(self.tester).sudo()._generate("rpc", "Script", None)

        self.assertEveryRouteRefuses(INVALID_KEY, key=rpc_key)

    def test_the_key_of_a_signed_out_computer_is_refused(self):
        self.first._sign_out()

        self.assertEveryRouteRefuses(INVALID_KEY, key=self.key)

    def test_a_revoked_computer_is_refused_at_once_and_the_persons_other_computer_keeps_working(self):
        self.first.with_user(self.tester).action_revoke()

        self.assertEveryRouteRefuses(INVALID_KEY, key=self.key)
        self.assertEqual(self.api("GET", "/devices", key=self.other_key).status_code, 200)

    def test_a_key_with_the_session_of_another_person_is_refused(self):
        self.authenticate(self.member.login, PASSWORD)

        self.assertEveryRouteRefuses(INVALID_KEY, key=self.key)

    def test_the_computer_of_a_call_is_the_one_of_its_key_whatever_the_request_names(self):
        named = {"X-Sync-Device-Id": str(self.second.id)}

        devices = self.api("GET", "/devices", key=self.key, headers=named).json()["devices"]
        self.api("POST", "/sign-out", key=self.key, headers=named)

        self.assertEqual([device["id"] for device in devices if device["current"]], [self.first.id])
        self.assertEqual(self.first.status, "signed_out")
        self.assertEqual(self.second.status, "signed_in")

    def test_a_person_who_lost_the_laboratory_files_permission_lists_nothing_and_still_signs_out_and_revokes(self):
        self.tester.write({"group_ids": [Command.unlink(persisted_id(self.env.ref(LABORATORY_FILES_GROUP)))]})

        self.assertApiRefused(PERMISSION_DENIED, self.api("GET", "/devices", key=self.key))
        self.assertEqual(self.api("POST", f"/devices/{self.second.id}/revoke", key=self.key).status_code, 200)
        self.assertEqual(self.api("POST", "/sign-out", key=self.key).status_code, 204)
        self.assertEqual((self.first | self.second).mapped("status"), ["signed_out", "revoked"])

from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from odoo.addons.sol_laboratory.constants.laboratory_files import INVALID_KEY, NOT_FOUND
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE


@tagged("post_install", "-at_install")
class TestLaboratoryApiDevices(LaboratoryApiCase):
    def setUp(self):
        super().setUp()
        self.key = self.signed_in_key(self.tester, "first-installation")
        self.other_key = self.signed_in_key(self.tester, "second-installation", name="AAS-PC")
        self.members_key = self.signed_in_key(self.member, "members-installation")
        devices = self.env[MODEL_LABORATORY_DEVICE]
        self.first = devices.search([("client_uid", "=", "first-installation")])
        self.second = devices.search([("client_uid", "=", "second-installation")])
        self.members = devices.search([("client_uid", "=", "members-installation")])

    def revoke(self, device, key=None):
        return self.api("POST", f"/devices/{device.id}/revoke", key=key or self.key)

    def test_a_person_lists_their_own_computers(self):
        devices = self.api("GET", "/devices", key=self.key).json()["devices"]

        self.assertEqual(sorted(device["id"] for device in devices), sorted((self.first | self.second).ids))
        self.assertEqual(
            {device["id"]: device["current"] for device in devices}, {self.first.id: True, self.second.id: False}
        )

    def test_revoking_another_computer_stops_its_key_and_the_caller_keeps_working(self):
        answer = self.revoke(self.second).json()["device"]

        self.assertEqual((answer["id"], answer["status"], answer["current"]), (self.second.id, "revoked", False))
        self.assertTrue(self.second.revoked_at)
        self.assertApiRefused(INVALID_KEY, self.api("GET", "/devices", key=self.other_key))
        self.assertEqual(self.api("GET", "/devices", key=self.key).status_code, 200)

    def test_a_computer_revokes_itself(self):
        answer = self.revoke(self.first).json()["device"]

        self.assertEqual((answer["status"], answer["current"]), ("revoked", True))
        self.assertApiRefused(INVALID_KEY, self.api("GET", "/devices", key=self.key))

    def test_revoking_again_changes_nothing(self):
        self.revoke(self.second)
        revoked_at = self.second.revoked_at

        self.assertEqual(self.revoke(self.second).status_code, 200)
        self.assertEqual(self.second.revoked_at, revoked_at)

    def test_another_persons_computer_is_not_found_and_stays_signed_in(self):
        self.assertApiRefused(NOT_FOUND, self.revoke(self.members))
        self.assertApiRefused(NOT_FOUND, self.revoke(self.env[MODEL_LABORATORY_DEVICE].browse(0)))
        self.assertEqual(self.members.status, "signed_in")

    def test_administrators_revoke_other_peoples_computers_in_the_back_office_only(self):
        administrators_key = self.signed_in_key(self.administrator, "administrators-installation")

        self.assertApiRefused(NOT_FOUND, self.revoke(self.members, administrators_key))
        self.assertEqual(self.members.status, "signed_in")

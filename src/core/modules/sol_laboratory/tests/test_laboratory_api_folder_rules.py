from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FOLDER_ARCHIVED,
    INVALID_REQUEST,
    NOT_FOUND,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER, MODEL_LABORATORY_SYNC_RULE


@tagged("post_install", "-at_install")
class TestLaboratoryApiFolderRules(LaboratoryApiCase):
    def setUp(self):
        super().setUp()
        self.key = self.signed_in_key(self.tester, "tester-installation")
        self.members_key = self.signed_in_key(self.member, "members-installation")
        self.path = f"/folders/{self.folder.id}/rules"

    def add(self, kind, pattern, key=None, **values):
        return self.api("POST", self.path, {"kind": kind, "pattern": pattern, **values}, key=key or self.key)

    def rules(self):
        return self.env[MODEL_LABORATORY_SYNC_RULE].search([("folder_id", "=", self.folder.id)])

    def test_the_owner_adds_a_rule_and_members_read_it(self):
        rule = self.add("prefix", "run-", recursive=False).json()["rule"]

        self.assertEqual(
            {key: rule[key] for key in ("kind", "pattern", "recursive", "enabled")},
            {"kind": "prefix", "pattern": "run-", "recursive": False, "enabled": True},
        )
        self.assertEqual(self.api("GET", self.path, key=self.members_key).json()["rules"], [rule])

    def test_adding_a_rule_the_folder_has_answers_with_that_rule(self):
        first = self.add("extension", ".PDF").json()["rule"]
        again = self.add("extension", "pdf", recursive=False).json()["rule"]

        self.assertEqual(again, first)
        self.assertEqual((first["pattern"], first["recursive"]), ("pdf", True))
        self.assertEqual(len(self.rules()), 1)

    def test_the_owner_changes_a_rule(self):
        rule = self.add("glob", "run-*.csv").json()["rule"]

        changed = self.api("PATCH", f"{self.path}/{rule['id']}", {"enabled": False, "recursive": False}, key=self.key)

        self.assertEqual(
            {key: changed.json()["rule"][key] for key in ("enabled", "recursive")},
            {"enabled": False, "recursive": False},
        )

    def test_a_rule_is_not_changed_into_one_the_folder_has(self):
        self.add("prefix", "run-")
        other = self.add("prefix", "cal-").json()["rule"]

        changed = self.api("PATCH", f"{self.path}/{other['id']}", {"pattern": "run-"}, key=self.key)

        self.assertApiRefused(INVALID_REQUEST, changed)
        self.assertEqual(sorted(self.rules().mapped("pattern")), ["cal-", "run-"])

    def test_a_rule_of_another_folder_is_not_found(self):
        rule = self.add("prefix", "run-").json()["rule"]
        other = self.env[MODEL_LABORATORY_FOLDER].create({"name": "AAS", "owner_id": self.tester.id})

        changed = self.api("PATCH", f"/folders/{other.id}/rules/{rule['id']}", {"enabled": False}, key=self.key)

        self.assertApiRefused(NOT_FOUND, changed)

    def test_removing_a_rule_twice_has_the_effect_of_once(self):
        rule = self.add("prefix", "run-").json()["rule"]

        self.assertEqual(self.api("DELETE", f"{self.path}/{rule['id']}", key=self.key).status_code, 204)
        self.assertEqual(self.api("DELETE", f"{self.path}/{rule['id']}", key=self.key).status_code, 204)
        self.assertFalse(self.rules())

    def test_a_rule_names_a_file_never_a_path(self):
        for kind, pattern in (
            ("prefix", "C:\\Data\\run-"),
            ("glob", "/home/lab/*.csv"),
            ("glob", "run-?.csv"),
            ("extension", "c/sv"),
        ):
            with self.subTest(kind=kind, pattern=pattern):
                self.assertApiRefused(INVALID_REQUEST, self.add(kind, pattern))
        rule = self.add("prefix", "run-").json()["rule"]
        changed = self.api("PATCH", f"{self.path}/{rule['id']}", {"pattern": "D:\\run-"}, key=self.key)
        self.assertApiRefused(INVALID_REQUEST, changed)
        self.assertEqual(self.rules().mapped("pattern"), ["run-"])

    def test_a_member_who_does_not_own_the_folder_does_not_change_its_rules(self):
        rule = self.add("prefix", "run-").json()["rule"]

        self.assertApiRefused(PERMISSION_DENIED, self.add("prefix", "cal-", self.members_key))
        changed = self.api("PATCH", f"{self.path}/{rule['id']}", {"enabled": False}, key=self.members_key)
        self.assertApiRefused(PERMISSION_DENIED, changed)
        self.assertApiRefused(PERMISSION_DENIED, self.api("DELETE", f"{self.path}/{rule['id']}", key=self.members_key))

    def test_the_rules_of_an_archived_folder_do_not_change(self):
        rule = self.add("prefix", "run-").json()["rule"]
        self.folder.with_user(self.administrator).action_archive_folder()

        self.assertApiRefused(FOLDER_ARCHIVED, self.add("prefix", "cal-"))
        self.assertApiRefused(FOLDER_ARCHIVED, self.api("DELETE", f"{self.path}/{rule['id']}", key=self.key))
        self.assertEqual(len(self.api("GET", self.path, key=self.key).json()["rules"]), 1)

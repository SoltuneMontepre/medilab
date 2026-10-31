from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .audit_case import AuditLookup
from .result_case import ResultCase
from odoo.addons.sol_laboratory.constants.jobs import ROLE_GRANTS_EXPIRE_JOB
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_ROLE_GRANT,
    MODEL_SCHEDULED_JOB,
)


@tagged("post_install", "-at_install")
class TestRoleGrants(AuditLookup, ResultCase):
    """The other tester backs up the head of the department until a date."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.head_role = cls.signing_chain().level_ids.sorted("sequence")[-1].role_id
        cls.today = cls.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()

    def give(self, date_end=None):
        return self.env[MODEL_ROLE_GRANT].create(
            {"person_id": self.other_tester.id, "role_id": self.head_role.id, "date_end": date_end or self.today}
        )

    def expire_after(self, day):
        with freeze_time(f"{day.isoformat()} 12:00:00"):
            self.env[MODEL_SCHEDULED_JOB]._run_key(ROLE_GRANTS_EXPIRE_JOB)

    def test_a_backup_signer_approves_until_the_end_of_their_date(self):
        self.give()

        self.assertIn(self.head_role, self.other_tester.role_ids)
        self.assertIn(self.head_role.group_id, self.other_tester.user_id.group_ids)
        result = self.enter()
        self.send(result)
        self.as_person(result, self.other_tester).action_sign()
        self.assertEqual(result.status, "approved")

    def test_a_role_given_until_a_date_is_removed_when_the_date_ends(self):
        grant = self.give()

        self.expire_after(self.today)
        self.assertIn(self.head_role, self.other_tester.role_ids)
        self.expire_after(self.today + timedelta(days=1))

        self.assertFalse(grant.exists())
        self.assertNotIn(self.head_role, self.other_tester.role_ids)
        self.assertNotIn(self.head_role.group_id, self.other_tester.user_id.group_ids)
        result = self.enter()
        self.send(result)
        self.assertFalse(self.as_person(result, self.other_tester).approval_can_sign)

    def test_giving_and_removing_the_role_are_in_the_audit_trail(self):
        grant = self.give()
        self.expire_after(self.today + timedelta(days=1))

        self.assertEqual(set(self.entries(grant).mapped("action")), {"create", "delete"})
        given, removed = [
            self.changes(entry)["role_ids"]
            for entry in self.entries(self.other_tester, "edit").sorted("id")
            if self.head_role.name in str(self.changes(entry).get("role_ids"))
        ]
        self.assertIn(self.head_role.name, given[1])
        self.assertNotIn(self.head_role.name, removed[1])

    def test_a_role_is_given_until_today_or_later_and_not_to_its_holder(self):
        with self.assertRaises(UserError):
            self.give(self.today - timedelta(days=1))
        with self.assertRaises(UserError):
            self.env[MODEL_ROLE_GRANT].create(
                {"person_id": self.head.id, "role_id": self.head_role.id, "date_end": self.today}
            )

    def test_taking_the_role_away_before_its_date_removes_the_date(self):
        grant = self.give(self.today + timedelta(days=7))

        self.other_tester.role_ids -= self.head_role

        self.assertFalse(grant.exists())

    def test_removing_the_date_takes_the_role_away(self):
        grant = self.give(self.today + timedelta(days=7))

        grant.unlink()

        self.assertNotIn(self.head_role, self.other_tester.role_ids)

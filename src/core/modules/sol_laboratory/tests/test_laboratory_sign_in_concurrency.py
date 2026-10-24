import uuid

from odoo.tests import tagged

from .laboratory_files_concurrency_case import LaboratoryFilesConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_files import DEVICE_REVOKED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE, MODEL_LABORATORY_SIGN_IN_ATTEMPT

# The administrator of a new database, whose password Odoo sets to admin and who holds every permission.
LOGIN = PASSWORD = "admin"


@tagged("post_install", "-at_install")
class TestLaboratorySignInConcurrency(LaboratoryFilesConcurrencyCase):
    """Two real database transactions signing in at once, the second one through Odoo's request retrying."""

    def setUp(self):
        super().setUp()
        self.client_uid = f"race-{uuid.uuid4().hex[:8]}"
        self.failing_login = f"race.nobody.{uuid.uuid4().hex[:8]}"
        self.last_entry_id = self.committed(self.last_entry)
        self.addCleanup(self.committed, self.remove)

    def last_entry(self, env):
        env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM medilab_audit_entry")
        return env.cr.fetchone()[0]

    def remove(self, env):
        # Computers are never deleted, so what these tests committed is removed with SQL.
        cr = env.cr
        cr.execute(
            "DELETE FROM medilab_audit_change WHERE entry_id IN (SELECT id FROM medilab_audit_entry WHERE id > %s)",
            [self.last_entry_id],
        )
        cr.execute("DELETE FROM medilab_audit_entry WHERE id > %s", [self.last_entry_id])
        cr.execute("DELETE FROM medilab_laboratory_device WHERE client_uid = %s", [self.client_uid])
        cr.execute("DELETE FROM res_users_apikeys WHERE name = 'Medilab Sync: race'")
        cr.execute("DELETE FROM medilab_laboratory_sign_in_attempt WHERE login = %s", [self.failing_login])

    def sign_in(self, env):
        device, _key = env[MODEL_LABORATORY_DEVICE]._sign_in(LOGIN, PASSWORD, self.client_uid, "race", "linux")
        return device

    def fail(self, env):
        attempts = env[MODEL_LABORATORY_SIGN_IN_ATTEMPT].sudo()
        attempts._record_failure(self.failing_login)
        return attempts.search([("login", "=", self.failing_login)])

    def test_two_first_sign_ins_of_one_installation_at_once_make_one_computer(self):
        attempts, second = self.race(self.sign_in, self.sign_in)

        def work(env):
            devices = env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", self.client_uid)])
            return devices.ids, devices.status

        self.assertEqual(attempts, 2)
        self.assertEqual(self.committed(work), ([second], "signed_in"))

    def test_two_failed_sign_ins_of_one_login_at_once_count_two(self):
        attempts, _second = self.race(self.fail, self.fail)

        def work(env):
            return env[MODEL_LABORATORY_SIGN_IN_ATTEMPT].search([("login", "=", self.failing_login)]).failures

        self.assertEqual(attempts, 2)
        self.assertEqual(self.committed(work), 2)

    def test_a_computer_revoked_while_it_signs_in_again_is_refused(self):
        self.committed(self.sign_in)

        def revoke(env):
            device = env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", self.client_uid)])
            device.action_revoke()
            return device

        attempts, refusal = self.race(revoke, self.sign_in)

        self.assertEqual(attempts, 2)
        self.assertEqual(refusal.code, DEVICE_REVOKED)

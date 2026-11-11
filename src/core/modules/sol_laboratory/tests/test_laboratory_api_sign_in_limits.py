import datetime

from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from odoo.addons.sol_laboratory.constants.laboratory_api import LONGEST_SIGN_IN_DELAY, SIGN_IN_FAILURE_WINDOW
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    INVALID_CREDENTIALS,
    PERMISSION_DENIED,
    TOO_MANY_ATTEMPTS,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_LABORATORY_SIGN_IN_ATTEMPT,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services.record_id import persisted_id
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

# Failed sign-ins of a login, and the delay its next one waits after the last failure.
DELAYS = {5: 1, 6: 2, 7: 4, 8: 8, 9: 16, 10: 32, 11: 60, 12: 60}
# The address the tests' requests come from.
TEST_ADDRESS = "127.0.0.1"


@tagged("post_install", "-at_install")
class TestLaboratoryApiSignInLimits(LaboratoryApiCase):
    """Signing in is slowed per login after failed attempts, never locked, with the counts in the database."""

    def setUp(self):
        super().setUp()
        # Odoo's own cooldown per address would refuse these tests' attempts first; one test turns it on again.
        self.env[MODEL_IR_CONFIG_PARAMETER].set_int("base.login_cooldown_after", 0)
        self.checked = []
        users = type(self.env[MODEL_RES_USERS])
        check_credentials = users._check_credentials

        def count_password_checks(user, credential, env):
            self.checked.append(user.login)
            return check_credentials(user, credential, env)

        self.patch(users, "_check_credentials", count_password_checks)

    def attempt(self, login=None):
        return self.env[MODEL_LABORATORY_SIGN_IN_ATTEMPT].search([("login", "=", login or self.tester.login)])

    def fail_sign_ins(self, times):
        """Fail to sign in the tester the times, each one once the delay of the one before has passed."""
        for _attempt in range(times):
            self.env.cr.execute(
                "UPDATE medilab_laboratory_sign_in_attempt SET failed_at = LEAST(failed_at, %s) WHERE login = %s",
                [self.ago(LONGEST_SIGN_IN_DELAY), self.tester.login],
            )
            self.assertApiRefused(INVALID_CREDENTIALS, self.api_sign_in(self.tester, "installation", password="wrong"))

    def age_last_failure(self, seconds, login=None):
        self.env.cr.execute(
            "UPDATE medilab_laboratory_sign_in_attempt SET failed_at = %s WHERE login = %s",
            [self.ago(seconds), login or self.tester.login],
        )

    @staticmethod
    def ago(seconds):
        return datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - datetime.timedelta(seconds=seconds)

    def test_five_failures_slow_the_next_attempt_before_its_password_is_checked(self):
        self.fail_sign_ins(5)
        checked = len(self.checked)

        response = self.api_sign_in(self.tester, "installation")

        self.assertApiRefused(TOO_MANY_ATTEMPTS, response)
        self.assertEqual(response.headers["Retry-After"], "1")
        self.assertEqual(len(self.checked), checked)
        self.assertEqual(self.attempt().failures, 5)

    def test_the_delay_doubles_from_one_second_up_to_sixty(self):
        self.fail_sign_ins(5)
        for failures, delay in DELAYS.items():
            with self.subTest(failures=failures):
                self.assertEqual(self.attempt().failures, failures)
                self.age_last_failure(delay - 0.5)
                early = self.api_sign_in(self.tester, "installation", password="wrong")
                self.assertApiRefused(TOO_MANY_ATTEMPTS, early)
                self.assertEqual(early.headers["Retry-After"], "1")

                self.age_last_failure(delay)
                self.fail_sign_ins(1)

    def test_the_person_signs_in_once_the_delay_has_passed_and_that_clears_the_count(self):
        self.fail_sign_ins(7)
        self.age_last_failure(4)

        self.assertEqual(self.api_sign_in(self.tester, "installation").status_code, 200)
        self.assertFalse(self.attempt())

    def test_a_right_password_refused_for_another_reason_also_clears_the_count(self):
        self.fail_sign_ins(2)
        self.tester.write({"group_ids": [Command.unlink(persisted_id(self.env.ref(LABORATORY_FILES_GROUP)))]})

        self.assertApiRefused(PERMISSION_DENIED, self.api_sign_in(self.tester, "installation"))
        self.assertFalse(self.attempt())

    def test_failures_older_than_the_window_are_forgotten(self):
        self.fail_sign_ins(6)
        self.age_last_failure(SIGN_IN_FAILURE_WINDOW.total_seconds())

        self.fail_sign_ins(1)

        self.assertEqual(self.attempt().failures, 1)

    def test_a_login_of_nobody_is_counted_and_slowed_the_same(self):
        body = {"login": "nobody", "password": "x", "client_uid": "installation", "name": "PC", "platform": "linux"}
        for _attempt in range(5):
            self.assertApiRefused(INVALID_CREDENTIALS, self.api("POST", "/sign-in", body))

        self.assertApiRefused(TOO_MANY_ATTEMPTS, self.api("POST", "/sign-in", body))
        self.assertEqual(self.attempt("nobody").failures, 5)
        self.assertEqual(self.api_sign_in(self.tester, "installation").status_code, 200)

    def test_odoos_cooldown_of_the_address_is_answered_as_too_many_attempts(self):
        self.env[MODEL_IR_CONFIG_PARAMETER].set_int("base.login_cooldown_after", 5)
        assert_instance(getattr(self.registry, "_login_failures"), dict)[TEST_ADDRESS] = (5, datetime.datetime.now())
        checked = len(self.checked)

        response = self.api_sign_in(self.tester, "installation")

        self.assertApiRefused(TOO_MANY_ATTEMPTS, response)
        self.assertLessEqual(int(response.headers["Retry-After"]), 60)
        self.assertEqual(len(self.checked), checked)
        self.assertFalse(self.attempt())

    def test_stale_counts_are_removed_by_odoos_autovacuum(self):
        self.fail_sign_ins(1)
        nobody = {"login": "nobody", "password": "x", "client_uid": "pc", "name": "PC", "platform": "linux"}
        self.assertApiRefused(INVALID_CREDENTIALS, self.api("POST", "/sign-in", nobody))
        self.age_last_failure(SIGN_IN_FAILURE_WINDOW.total_seconds(), "nobody")

        self.env[MODEL_LABORATORY_SIGN_IN_ATTEMPT]._gc_forgotten_failures()

        kept = self.env[MODEL_LABORATORY_SIGN_IN_ATTEMPT].search([("login", "in", ["nobody", self.tester.login])])
        self.assertEqual(kept.mapped("login"), [self.tester.login])

"""Adversarial regressions for initialization, persistence and readiness."""

import json
import unittest

from runtime import PASSWORD, Runtime, engine


class TestReview(unittest.TestCase):
    def runtime(self, **kwargs):
        runtime = Runtime(**kwargs)
        runtime.env.update(CB_VERIFY_NAME="operator", CB_VERIFY_PASSWORD=PASSWORD)
        self.addCleanup(runtime.close)
        return runtime

    def test_duplicate_json_keys_are_rejected_without_data_loss(self):
        runtime = self.runtime()
        path = "GlobalConfiguration/.dbeaver/data-sources.json"
        original = '{"connections":{"first":{"name":"First"}},"connections":{"second":{"name":"Second"}}}'
        runtime.write(path, original)
        self.assertNotEqual(runtime.prepare(check=False).returncode, 0)
        self.assertEqual(runtime.read(path), original)

    def test_unrecognized_or_credential_only_workspace_is_not_fresh(self):
        for path in ("OldProject/Scripts/retained.sql", "GlobalConfiguration/.dbeaver/credentials-config.json"):
            with self.subTest(path=path):
                runtime = self.runtime()
                runtime.write(path, "existing-data")
                self.assertNotEqual(runtime.prepare(check=False).returncode, 0)
                self.assertEqual(runtime.read(path), "existing-data")

    def test_supplemental_managed_connection_is_not_shadowed(self):
        runtime = self.runtime()
        path = "GlobalConfiguration/.dbeaver/data-sources-personal.json"
        original = json.dumps({"connections": {"medilab-postgres": {"name": "User-managed override"}}})
        runtime.write(path, original)
        runtime.prepare()
        self.assertEqual(runtime.read(path), original)
        self.assertEqual(
            runtime.helper(
                "test ! -e workspace/GlobalConfiguration/.dbeaver/data-sources.json", check=False
            ).returncode,
            0,
        )

    def test_provisioning_refuses_a_running_workspace(self):
        runtime = self.runtime()
        runtime.prepare()
        runtime.start()
        runtime.wait()
        self.assertEqual(runtime.login(), "operator")
        before = runtime.read("GlobalConfiguration/.dbeaver/data-sources.json")
        self.assertNotEqual(runtime.prepare(check=False).returncode, 0)
        self.assertEqual(runtime.read("GlobalConfiguration/.dbeaver/data-sources.json"), before)
        self.assertEqual(runtime.login(), "operator")

    def test_fabricated_completion_does_not_make_accountless_workspace_ready(self):
        runtime = self.runtime(guarded=False, admin="admin")
        runtime.start()
        runtime.wait(configuration_mode=True)
        runtime.stop()
        runtime.write(".data/.cloudbeaver.runtime.conf", '{"server":{"serverName":"Regression"}}')
        runtime.guarded = True
        runtime.env["CB_ADMIN_NAME"] = "operator"
        runtime.prepare()
        runtime.start()
        runtime.wait()
        self.assertFalse(runtime.ready())
        logs = engine("logs", runtime.name).stdout
        self.assertNotIn("Configure CB database security", logs)

    def test_readiness_rejects_wrong_credentials_without_changing_existing_password(self):
        runtime = self.runtime()
        runtime.prepare()
        runtime.start()
        runtime.wait()
        self.assertEqual(runtime.login(), "operator")
        runtime.stop()
        runtime.env["CB_VERIFY_PASSWORD"] = "WrongVerificationPassword9"
        runtime.start()
        runtime.wait()
        self.assertFalse(runtime.ready())
        self.assertFalse(runtime.ready())
        self.assertEqual(runtime.login(), "operator")

    def test_acknowledged_accounts_survive_immediate_process_kill(self):
        runtime = self.runtime()
        runtime.prepare()
        runtime.start()
        runtime.wait()
        runtime.login()
        for attempt in range(3):
            user = f"committed-{attempt}"
            runtime.query(f'{{ createUser(userId: "{user}", enabled: true) {{ userId }} }}')
            engine("kill", "--signal", "KILL", runtime.name)
            engine("start", runtime.name)
            runtime.wait()
            self.assertEqual(runtime.login(), "operator")
            users = runtime.query("{ listUsers(page: {}, filter: {}) { userId } }")["data"]["listUsers"]
            self.assertIn(user, [value["userId"] for value in users])

    def test_verification_session_rotation_failure_latch_and_transient_recovery(self):
        runtime = self.runtime()
        runtime.helper(
            'gson=(server/plugins/com.google.gson_*.jar); javac -cp "${gson[0]}" -d /bootstrap-bin '
            "/bootstrap/*.java /regression/AuthenticationTest.java; "
            'java -cp "/bootstrap-bin:${gson[0]}" AuthenticationTest'
        )

    def test_existing_default_database_reopens_without_management_credential_change(self):
        runtime = self.runtime()
        synchronous_url = runtime.env.pop("CLOUDBEAVER_DB_URL")
        runtime.prepare()
        runtime.start()
        runtime.wait()
        self.assertEqual(runtime.login(), "operator")
        runtime.stop()
        before = runtime.helper("sha256sum workspace/.data/.database-credentials.dat").stdout
        runtime.env["CLOUDBEAVER_DB_URL"] = synchronous_url
        runtime.start()
        runtime.wait()
        self.assertTrue(runtime.ready())
        self.assertEqual(runtime.login(), "operator")
        self.assertEqual(runtime.helper("sha256sum workspace/.data/.database-credentials.dat").stdout, before)

    def test_explicit_first_installation_recovery_preserves_partial_database(self):
        runtime = self.runtime(guarded=False, admin="admin")
        runtime.start()
        runtime.wait(configuration_mode=True)
        inventory = "{ listUsers(page: {}, filter: {}) { userId } listTeams { teamId } }"
        with self.assertRaisesRegex(AssertionError, "not available in server configuration mode"):
            runtime.query(inventory)
        self.assertIn("User or team 'admin' already exists", engine("logs", runtime.name).stdout)
        runtime.stop()
        runtime.helper("test -s workspace/.data/cb.h2v2.dat.mv.db")
        runtime.env["CB_ADMIN_NAME"] = "operator"
        self.assertNotEqual(runtime.prepare(check=False).returncode, 0)
        # This fixture has a known fresh-volume history; an arbitrary existing database does not authorize setup.
        runtime.start()
        runtime.wait()
        self.assertEqual(runtime.login(), "operator")
        after = runtime.query(inventory)["data"]
        self.assertEqual(after["listUsers"], [{"userId": "operator"}])
        self.assertEqual({team["teamId"] for team in after["listTeams"]}, {"admin", "user"})
        runtime.stop()
        runtime.guarded = True
        runtime.prepare()
        runtime.start()
        runtime.wait()
        self.assertTrue(runtime.ready())
        self.assertEqual(runtime.login(), "operator")
        self.assertEqual(runtime.query(inventory)["data"], after)


if __name__ == "__main__":
    unittest.main()

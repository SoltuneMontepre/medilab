"""Verify the pinned server's local-login protocol without changing persisted credentials."""

import hashlib
import unittest

from runtime import PASSWORD, Runtime, engine


class TestAuthProtocol(unittest.TestCase):
    def runtime(self):
        runtime = Runtime()
        self.addCleanup(runtime.close)
        return runtime

    def test_other_wire_hashes_are_rejected_without_password_or_account_changes(self):
        candidates = {
            "raw": PASSWORD,
            "sha256": hashlib.sha256(PASSWORD.encode()).hexdigest().upper(),
            "scrypt": hashlib.scrypt(PASSWORD.encode(), salt=b"synthetic-protocol-vector", n=1024, r=8, p=1).hex(),
        }
        for algorithm, candidate in candidates.items():
            with self.subTest(algorithm=algorithm):
                runtime = self.runtime()
                runtime.prepare()
                runtime.start()
                runtime.wait()
                result = runtime.query(
                    'query($credentials: Object!) { authLogin(provider: "local", '
                    "credentials: $credentials) { authStatus } }",
                    {"credentials": {"user": "operator", "password": candidate}},
                    errors=True,
                )
                if not result.get("errors"):
                    self.assertEqual(result["data"]["authLogin"]["authStatus"], "ERROR")
                active = runtime.query("{ activeUser { isAnonymous } }")["data"]["activeUser"]
                self.assertTrue(active is None or active["isAnonymous"])
                self.assertEqual(runtime.login(), "operator")
                users = "{ listUsers(page: {}, filter: {}) { userId enabled } }"
                expected = {"listUsers": [{"userId": "operator", "enabled": True}]}
                self.assertEqual(runtime.query(users)["data"], expected)
                engine("restart", "--time", "30", runtime.name)
                runtime.wait()
                self.assertEqual(runtime.login(), "operator")
                self.assertEqual(runtime.query(users)["data"], expected)

    def test_unicode_password_authenticates_in_java_probe_and_python_client(self):
        runtime = self.runtime()
        password = "Regression9-ệ\"'\\`$"
        runtime.env.update(CB_ADMIN_PASSWORD=password, CB_VERIFY_PASSWORD=password)
        runtime.prepare()
        runtime.start()
        runtime.wait()
        self.assertTrue(runtime.ready())
        self.assertEqual(runtime.login(password=password), "operator")
        engine("restart", "--time", "30", runtime.name)
        runtime.wait()
        self.assertTrue(runtime.ready())
        self.assertEqual(runtime.login(password=password), "operator")


if __name__ == "__main__":
    unittest.main()

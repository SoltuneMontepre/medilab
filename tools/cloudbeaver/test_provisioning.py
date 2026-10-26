"""Provisioning diagnostics must explain safe failure categories without echoing workspace contents."""

import unittest

from runtime import Runtime


class TestProvisioning(unittest.TestCase):
    def runtime(self):
        runtime = Runtime()
        self.addCleanup(runtime.close)
        return runtime

    def test_missing_credentials_are_reported_without_values(self):
        runtime = self.runtime()
        runtime.env["DB_PASSWORD"] = ""
        runtime.env["DB_USER"] = "SECRET-USER-CANARY"
        result = runtime.prepare(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DB_USER or DB_PASSWORD missing", result.stderr)
        self.assertNotIn("SECRET-USER-CANARY", result.stderr)

    def test_duplicate_identifiers_are_reported_without_connection_content(self):
        runtime = self.runtime()
        original = '{"connections":{"SECRET-ID-CANARY":{"name":"PRIVATE-CONNECTION"}}}'
        for suffix in ("", "-extra"):
            runtime.write(f"GlobalConfiguration/.dbeaver/data-sources{suffix}.json", original)
        result = runtime.prepare(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Duplicate connection identifier", result.stderr)
        self.assertNotIn("SECRET-ID-CANARY", result.stderr)
        self.assertNotIn("PRIVATE-CONNECTION", result.stderr)
        self.assertEqual(runtime.read("GlobalConfiguration/.dbeaver/data-sources.json"), original)

    def test_symlink_is_reported_without_following_or_replacing_it(self):
        runtime = self.runtime()
        runtime.helper(
            "mkdir -p workspace/GlobalConfiguration/.dbeaver; "
            "ln -s /private-SECRET-CANARY workspace/GlobalConfiguration/.dbeaver/data-sources-extra.json"
        )
        result = runtime.prepare(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Symbolic link in data-sources", result.stderr)
        self.assertNotIn("SECRET-CANARY", result.stderr)
        runtime.helper("test -L workspace/GlobalConfiguration/.dbeaver/data-sources-extra.json")

    def test_parser_diagnostic_does_not_echo_secret_containing_json(self):
        runtime = self.runtime()
        path = "GlobalConfiguration/.dbeaver/data-sources.json"
        original = '{"SECRET-CANARY":{"password":"PRIVATE-CREDENTIAL"}, "broken":'
        runtime.write(path, original)
        result = runtime.prepare(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("provisioning blocked", result.stderr)
        for secret in ("SECRET-CANARY", "PRIVATE-CREDENTIAL"):
            self.assertNotIn(secret, result.stderr)
        self.assertEqual(runtime.read(path), original)


if __name__ == "__main__":
    unittest.main()

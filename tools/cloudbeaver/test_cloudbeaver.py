"""Regression tests using CloudBeaver 26.2.2 and synthetic data. Run from the repository root:

python3 -m unittest discover -s tools/cloudbeaver -v
Requires a local Docker-compatible engine; CONTAINER_ENGINE selects an alternative.
"""

import json
import time
import unittest
import urllib.request

from runtime import SPECIAL_PASSWORD, SPECIAL_USER, Runtime, engine


class TestCloudBeaver(unittest.TestCase):
    def runtime(self, **kwargs):
        runtime = Runtime(**kwargs)
        self.addCleanup(runtime.close)
        return runtime

    def test_collision_reproduces_exact_upstream_failure(self):
        runtime = self.runtime(guarded=False, admin="admin")
        runtime.start()
        runtime.wait(configuration_mode=True)
        logs = engine("logs", runtime.name).stdout
        self.assertIn("User or team 'admin' already exists", logs)
        self.assertIn("Management database connection established", logs)
        result = runtime.helper(
            "test -f workspace/.data/cb.h2v2.dat.mv.db && test ! -e workspace/.data/.cloudbeaver.runtime.conf"
        )
        self.assertEqual(result.returncode, 0)
        with urllib.request.urlopen(f"http://127.0.0.1:{runtime.port}/status", timeout=5) as response:
            self.assertEqual(json.load(response)["health"], "ok")
        runtime.stop()
        # A renamed Secret must not silently re-run setup against this H2 database.
        runtime.env["CB_ADMIN_NAME"] = "operator"
        self.assertNotEqual(runtime.prepare(check=False).returncode, 0)

    def test_fresh_reserved_identifiers_rejected_before_h2_creation(self):
        for admin in ("admin", "ADMIN", "user", "UsEr", " admin ", ""):
            with self.subTest(admin=admin):
                runtime = self.runtime(admin=admin)
                self.assertNotEqual(runtime.prepare(check=False).returncode, 0)
                self.assertEqual(runtime.helper("test ! -e workspace/.data").returncode, 0)

    def test_durable_initialization_container_restart_and_volume_reattachment(self):
        runtime = self.runtime()
        runtime.prepare()
        runtime.start()
        runtime.wait()
        self.assertTrue(runtime.ready())
        self.assertEqual(runtime.login(), "operator")
        subjects = "{ listUsers(page: {}, filter: {}) { userId } listTeams { teamId } }"
        original = runtime.query(subjects)["data"]
        self.assertEqual([user["userId"] for user in original["listUsers"]], ["operator"])
        self.assertIn("admin", [team["teamId"] for team in original["listTeams"]])
        # A user-created account must also survive; it is not a bootstrap subject.
        runtime.query('{ createUser(userId: "existing-user", enabled: true) { userId } }')
        original = runtime.query(subjects)["data"]
        for _ in range(2):
            engine("restart", "--time", "30", runtime.name)
            runtime.wait()
            self.assertTrue(runtime.ready())
            self.assertEqual(runtime.login(), "operator")
            self.assertEqual(runtime.query(subjects)["data"], original)
        runtime.stop()
        saved_runtime = runtime.read(".data/.cloudbeaver.runtime.conf")
        # An installation predating the guard has no attempt marker.
        runtime.helper("rm workspace/.medilab-bootstrap-attempt")
        parsed = json.loads(saved_runtime)
        self.assertEqual(parsed["server"]["serverName"], "Regression")
        parsed.setdefault("app", {})["supportsCustomConnections"] = False
        runtime.write(".data/.cloudbeaver.runtime.conf", json.dumps(parsed))
        # Mimic replacement Pod: new ephemeral compiled classes, same persistent workspace.
        replacement = self.runtime(volume=runtime.volume, admin="admin")
        replacement.env["CB_ADMIN_PASSWORD"] = "DeliberatelyDifferent9"
        replacement.prepare()
        replacement.start()
        replacement.wait()
        self.assertTrue(replacement.ready())
        self.assertEqual(replacement.login(), "operator")
        self.assertEqual(replacement.query(subjects)["data"], original)
        self.assertFalse(
            replacement.query("{ serverConfig { supportsCustomConnections } }")["data"]["serverConfig"][
                "supportsCustomConnections"
            ]
        )
        logs = engine("logs", replacement.name).stdout
        self.assertNotIn("Configure CB database security", logs)
        self.assertNotIn("User or team 'admin' already exists", logs)
        replacement.stop()
        # Missing completion state requires recovery, and must leave H2 byte-for-byte unchanged.
        before = replacement.helper("sha256sum workspace/.data/cb.h2v2.dat.mv.db").stdout
        replacement.helper("mv workspace/.data/.cloudbeaver.runtime.conf workspace/.data/runtime.saved")
        self.assertNotEqual(replacement.prepare(check=False).returncode, 0)
        self.assertEqual(replacement.helper("sha256sum workspace/.data/cb.h2v2.dat.mv.db").stdout, before)
        replacement.helper("mv workspace/.data/runtime.saved workspace/.data/.cloudbeaver.runtime.conf")
        replacement.prepare()
        replacement.start()
        replacement.wait()
        self.assertEqual(replacement.login(), "operator")

    def test_interrupted_bootstrap_is_not_retried(self):
        runtime = self.runtime()
        runtime.prepare()
        runtime.helper(
            'gson=(server/plugins/com.google.gson_*.jar); java -cp "/bootstrap-bin:${gson[0]}" Workspace start'
        )
        self.assertNotEqual(runtime.prepare(check=False).returncode, 0)
        runtime.start()
        result = engine("wait", runtime.name)
        self.assertNotEqual(result.stdout.strip(), "0")
        self.assertEqual(runtime.helper("test ! -e workspace/.data/cb.h2v2.dat.mv.db").returncode, 0)

    def test_incomplete_existing_workspace_and_runtime_without_h2_rejected(self):
        fixtures = {
            ".data/.cloudbeaver.runtime.conf": '{"server":{"serverName":"Existing"}}',
            ".data/cb.h2v2.dat.mv.db": "synthetic-h2-marker",
            ".metadata/previous-start": "previous initialization",
        }
        for path, data in fixtures.items():
            with self.subTest(path=path):
                runtime = self.runtime()
                runtime.write(path, data)
                before = runtime.read(path)
                self.assertNotEqual(runtime.prepare(check=False).returncode, 0)
                self.assertEqual(runtime.read(path), before)

    def test_empty_h2_with_completed_runtime_is_not_reinitialized(self):
        runtime = self.runtime()
        runtime.write(".data/.cloudbeaver.runtime.conf", '{"server":{"serverName":"Existing"}}')
        runtime.write(".data/cb.h2v2.dat.mv.db", "")
        self.assertNotEqual(runtime.prepare(check=False).returncode, 0)
        self.assertEqual(runtime.read(".data/cb.h2v2.dat.mv.db"), "")

    def test_provisioning_preserves_custom_connections_and_escapes_credentials(self):
        runtime = self.runtime()
        runtime.prepare()
        runtime.start()
        runtime.wait()
        runtime.stop()
        path = "GlobalConfiguration/.dbeaver/data-sources.json"
        original = {
            "folders": {"custom": {"name": "Research"}},
            "connections": {"user-managed": {"name": "Private", "custom": [1, True, "unicode-ệ"]}},
            "unknown": {"keep": True},
        }
        runtime.write(path, json.dumps(original))
        runtime.write("GlobalConfiguration/.dbeaver/credentials-config.json", "encrypted-existing-credentials")
        runtime.prepare()
        first = runtime.read(path)
        data = json.loads(first)
        self.assertEqual(data["connections"]["user-managed"], original["connections"]["user-managed"])
        self.assertEqual(data["unknown"], original["unknown"])
        self.assertEqual(data["folders"], original["folders"])
        auth = data["connections"]["medilab-postgres"]["configuration"]["auth-properties"]
        self.assertEqual(auth["userName"], SPECIAL_USER)
        self.assertEqual(auth["userPassword"], SPECIAL_PASSWORD)
        self.assertEqual(
            runtime.helper("stat -c %a workspace/GlobalConfiguration/.dbeaver/data-sources.json").stdout.strip(), "600"
        )
        runtime.env["DB_PASSWORD"] = "NewSecretMustNotReplaceExisting9"
        runtime.prepare()
        self.assertEqual(runtime.read(path), first)
        self.assertEqual(
            runtime.read("GlobalConfiguration/.dbeaver/credentials-config.json"), "encrypted-existing-credentials"
        )
        self.assertEqual(
            runtime.helper(
                "stat -c %a workspace/GlobalConfiguration/.dbeaver/.medilab-before-provision-*.json"
            ).stdout.strip(),
            "600",
        )

    def test_malformed_connections_are_never_replaced(self):
        runtime = self.runtime()
        path = "GlobalConfiguration/.dbeaver/data-sources.json"
        runtime.write(path, "{malformed:")
        self.assertNotEqual(runtime.prepare(check=False).returncode, 0)
        self.assertEqual(runtime.read(path), "{malformed:")

    def test_saved_special_character_credentials_connect_and_survive_recreation(self):
        runtime = self.runtime()
        runtime.network = runtime.name + "-network"
        database = runtime.name + "-postgres"
        engine("network", "create", runtime.network)

        def cleanup_network():
            runtime.stop()
            engine("rm", "-f", "-v", database, check=False)
            engine("network", "rm", runtime.network, check=False)

        self.addCleanup(cleanup_network)
        engine(
            "run",
            "-d",
            "--name",
            database,
            "--network",
            runtime.network,
            "--network-alias",
            "postgres-regression",
            "-e",
            "POSTGRES_USER=postgres",
            "-e",
            "POSTGRES_PASSWORD=BootstrapRegression9",
            "-e",
            "POSTGRES_DB=medilab",
            "docker.io/library/postgres:18.4",
        )
        deadline = time.monotonic() + 60
        while engine(
            "exec", database, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", "medilab", check=False
        ).returncode:
            if time.monotonic() >= deadline:
                self.fail("Isolated PostgreSQL did not become ready.")
            time.sleep(1)
        quoted_user = '"' + SPECIAL_USER.replace('"', '""') + '"'
        quoted_password = "'" + SPECIAL_PASSWORD.replace("'", "''") + "'"
        engine(
            "exec",
            "-i",
            database,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "medilab",
            input=f"CREATE ROLE {quoted_user} LOGIN PASSWORD {quoted_password};\n",
        )
        runtime.env["DB_HOST"] = "postgres-regression"
        runtime.prepare()
        path = "GlobalConfiguration/.dbeaver/data-sources.json"
        data = json.loads(runtime.read(path))
        data["connections"]["user-managed"] = {
            **data["connections"]["medilab-postgres"],
            "name": "User-managed connection",
        }
        runtime.write(path, json.dumps(data))
        runtime.start()
        runtime.wait()
        self.assertEqual(runtime.login(), "operator")
        connect = (
            'mutation { initConnection(id: "medilab-postgres", projectId: "g_GlobalConfiguration", '
            "saveCredentials: true, sharedCredentials: true) { id connected } }"
        )
        result = runtime.query(connect, errors=True)
        if result.get("errors"):
            messages = json.dumps(result["errors"], ensure_ascii=False)
            for secret in (SPECIAL_PASSWORD, json.dumps(SPECIAL_PASSWORD)[1:-1]):
                messages = messages.replace(secret, "[REDACTED]")
            self.fail(messages)
        self.assertTrue(result["data"]["initConnection"]["connected"])
        runtime.stop()
        saved_connections = runtime.read(path)
        replacement = self.runtime(volume=runtime.volume, admin="admin")
        replacement.network = runtime.network
        replacement.env["DB_PASSWORD"] = "MustNotOverwriteSavedCredential9"
        replacement.prepare()
        self.assertEqual(replacement.read(path), saved_connections)
        preserved = json.loads(replacement.read(path))
        self.assertIn("user-managed", preserved["connections"])
        replacement.start()
        replacement.wait()
        self.assertEqual(replacement.login(), "operator")
        self.assertTrue(replacement.query(connect)["data"]["initConnection"]["connected"])
        self.assertEqual(
            replacement.query('{ connectionInfo(projectId: "g_GlobalConfiguration", id: "user-managed") { name } }')[
                "data"
            ]["connectionInfo"]["name"],
            "User-managed connection",
        )
        replacement.stop()

    def test_readiness_rejects_incomplete_runtime_even_when_graphql_responds(self):
        runtime = self.runtime(guarded=False, admin="admin")
        runtime.start()
        runtime.wait(configuration_mode=True)
        runtime.helper(
            'gson=(server/plugins/com.google.gson_*.jar); javac -cp "${gson[0]}" -d /bootstrap-bin /bootstrap/*.java'
        )
        self.assertFalse(runtime.ready())
        # Runtime file alone cannot make an in-memory configuration-mode server ready.
        runtime.write(".data/.cloudbeaver.runtime.conf", '{"server":{"serverName":"Synthetic"}}')
        self.assertFalse(runtime.ready())

    def test_readiness_rejects_errors_invalid_types_and_unavailable_server(self):
        runtime = self.runtime()
        runtime.helper(
            'gson=(server/plugins/com.google.gson_*.jar); javac -cp "${gson[0]}" -d /bootstrap-bin '
            '/bootstrap/*.java /regression/ReadinessTest.java; java -cp "/bootstrap-bin:${gson[0]}" ReadinessTest'
        )


if __name__ == "__main__":
    unittest.main()

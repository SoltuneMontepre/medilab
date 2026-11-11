"""Fingerprint contracts use fake owned services; no runtime or credentials are accessed."""

import contextlib
import copy
import io
import json
import os
import runpy
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import local_acceptance_snapshot as snapshot

OWNER = "8ef7dc59-230f-4a57-8854-85ff306f38d9"
DATABASE = "a3241579-4da2-4cdf-a589-e522c18ed8f0"


class BucketFingerprintTests(unittest.TestCase):
    def execute(self, objects, **environment):
        values = {
            "BUCKET_LABORATORY_ADDRESS": "http://garage:3900",
            "BUCKET_LABORATORY_NAME": "owned-bucket",
            "BUCKET_LABORATORY_REGION": "garage",
            "BUCKET_LABORATORY_ACCESS_KEY": "private-access",
            "BUCKET_LABORATORY_SECRET_KEY": "private-secret",
            **environment,
        }
        client = Mock()
        client.get_paginator.return_value.paginate.return_value = [
            {
                "Contents": [
                    {"Key": key, "Size": len(value)} for key, value in objects.items()
                ]
            }
        ]
        client.get_object.side_effect = lambda **kwargs: {
            "Body": io.BytesIO(objects[kwargs["Key"]])
        }
        boto = types.ModuleType("boto3")
        boto.client = Mock(return_value=client)
        config = types.ModuleType("botocore.config")
        config.Config = Mock(side_effect=lambda **kwargs: kwargs)
        output = io.StringIO()
        with (
            patch.dict(os.environ, values, clear=True),
            patch.dict(sys.modules, {"boto3": boto, "botocore.config": config}),
            patch.object(
                sys,
                "stdin",
                io.StringIO(
                    json.dumps({"bucket": "owned-bucket", "database_uuid": DATABASE})
                ),
            ),
            patch.object(sys, "excepthook"),
            contextlib.redirect_stdout(output),
            tempfile.TemporaryDirectory(prefix="owned bucket probe ") as temporary,
        ):
            probe = Path(temporary) / "probe.py"
            probe.write_text(snapshot.BUCKET_SNAPSHOT, encoding="utf-8")
            runpy.run_path(str(probe))
        return json.loads(output.getvalue()), boto, output.getvalue()

    def test_exact_content_fingerprint_changes_with_bytes_without_emitting_keys_or_contents(
        self,
    ):
        objects = {
            "private-document-key": b"private document contents",
            ".medilab-database": DATABASE.encode(),
        }
        result, boto, text = self.execute(objects)
        self.assertEqual(result["objects"], 2)
        self.assertTrue(result["owner_marker"]["matches_database"])
        for private in (
            "private-document-key",
            "private document contents",
            "private-access",
            "private-secret",
            DATABASE,
        ):
            self.assertNotIn(private, text)
        changed, _, _ = self.execute(
            {**objects, "private-document-key": b"changed same resource"}
        )
        self.assertEqual(changed["objects"], result["objects"])
        self.assertNotEqual(changed["sha256"], result["sha256"])
        kwargs = boto.client.call_args.kwargs
        self.assertEqual(kwargs["endpoint_url"], "http://garage:3900")
        self.assertEqual(kwargs["config"]["proxies"], {})
        self.assertEqual(kwargs["config"]["s3"], {"addressing_style": "path"})

    def test_foreign_or_oversized_database_marker_cannot_be_accepted(self):
        result, _, _ = self.execute({".medilab-database": b"another database"})
        self.assertTrue(result["owner_marker"]["present"])
        self.assertFalse(result["owner_marker"]["matches_database"])
        with self.assertRaises(ValueError):
            self.execute({".medilab-database": b"x" * 129})

    def test_endpoint_bucket_or_missing_explicit_credentials_refuse_before_client_creation(
        self,
    ):
        for values in (
            {"BUCKET_LABORATORY_ADDRESS": "https://foreign.invalid"},
            {"BUCKET_LABORATORY_NAME": "foreign-bucket"},
            {"BUCKET_LABORATORY_ACCESS_KEY": ""},
            {"BUCKET_LABORATORY_SECRET_KEY": ""},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.execute({}, **values)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="acceptance kiểm tra ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.config = {
            f"DATA_{index}_VOLUME": f"owned_volume_{index}" for index in range(7)
        }
        self.marker = {
            "status": "completed",
            "project": "owned",
            "owner": OWNER,
            "engine": "engine",
            "config": self.config,
        }
        self.resources = {
            "containers": [
                self.container(service, index)
                for index, service in enumerate(("postgres", "odoo", "onlyoffice"), 1)
            ],
            "volumes": [
                {
                    "Name": name,
                    "CreatedAt": "2026-10-29T00:00:00Z",
                    "Labels": {snapshot.bootstrap.OWNER_LABEL: OWNER},
                }
                for name in self.config.values()
            ],
        }
        self.runtime = {"bucket": "owned-bucket"}
        self.bucket = {
            "objects": 13,
            "sha256": "a" * 64,
            "owner_marker": {"present": True, "matches_database": True},
        }
        for relative in (
            "jwt",
            "tls/ca.key",
            "tls/server/tls.key",
            "tls/server/tls.crt",
            "tls/public/ca.crt",
            "tls/public/bundle.crt",
            "tls/public-roots.json",
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"private owned fixture")
        (self.root / "runtime.json").write_text(
            json.dumps(self.runtime), encoding="utf-8"
        )

    def container(self, service, index):
        return {
            "Id": str(index) * 64,
            "Config": {
                "Labels": {
                    "com.docker.compose.service": service,
                    snapshot.bootstrap.OWNER_LABEL: OWNER,
                }
            },
            "State": {"Running": True},
        }

    def select(self, resources=None):
        with (
            patch.object(
                snapshot.local_compose,
                "_resolve",
                return_value=("owned", self.marker, [], {}),
            ),
            patch.object(
                snapshot.bootstrap, "_assert_local_engine", return_value="engine"
            ),
            patch.object(
                snapshot.bootstrap,
                "_resources",
                return_value=resources or self.resources,
            ),
        ):
            return snapshot.selected("owned", OWNER)

    def test_selection_requires_running_unique_owned_services_and_same_engine(self):
        self.assertEqual(set(self.select()[2]), {"postgres", "odoo", "onlyoffice"})
        mutations = []
        resources = copy.deepcopy(self.resources)
        resources["containers"][0]["State"]["Running"] = False
        mutations.append(resources)
        resources = copy.deepcopy(self.resources)
        resources["containers"][0]["Config"]["Labels"][
            snapshot.bootstrap.OWNER_LABEL
        ] = "foreign"
        mutations.append(resources)
        resources = copy.deepcopy(self.resources)
        resources["containers"].append(resources["containers"][0])
        mutations.append(resources)
        for resources in mutations:
            with (
                self.subTest(resources=resources),
                self.assertRaises(snapshot.SnapshotError),
            ):
                self.select(resources)
        with (
            patch.object(
                snapshot.local_compose,
                "_resolve",
                return_value=("owned", self.marker, [], {}),
            ),
            patch.object(
                snapshot.bootstrap, "_assert_local_engine", return_value="different"
            ),
            self.assertRaises(snapshot.SnapshotError),
        ):
            snapshot.selected("owned", OWNER)

    def capture(self, *, database_uuid=DATABASE, volumes=None, runtime=None):
        containers = {
            service: str(index) * 64
            for index, service in enumerate(("postgres", "odoo", "onlyoffice"), 1)
        }
        resources = {
            **self.resources,
            "volumes": volumes if volumes is not None else self.resources["volumes"],
        }
        with (
            patch.object(
                snapshot, "selected", return_value=(self.marker, resources, containers)
            ),
            patch.object(
                snapshot,
                "database_read",
                side_effect=[database_uuid, '[{"id":1}]', '[{"id":2}]'],
            ) as reads,
            patch.object(
                snapshot.onlyoffice_state,
                "read_state",
                return_value={"status": "completed"},
            ),
            patch.object(
                snapshot.onlyoffice_state, "state_directory", return_value=self.root
            ),
            patch.object(
                snapshot.onlyoffice_state,
                "checked_path",
                side_effect=lambda path, **kwargs: path,
            ),
            patch.object(snapshot.bootstrap, "_compose_environment", return_value={}),
            patch(
                "onlyoffice.runtime_config",
                return_value=runtime if runtime is not None else self.runtime,
            ),
            patch.object(
                snapshot,
                "output",
                side_effect=[json.dumps(self.bucket), "b" * 64 + "  private"],
            ),
        ):
            return snapshot.capture("owned", OWNER), reads

    def test_snapshot_hashes_data_and_private_bytes_and_requires_exact_seven_volume_identities(
        self,
    ):
        result, reads = self.capture()
        self.assertEqual(result["data"]["files"]["rows"], 1)
        self.assertEqual(len(result["volumes"]), 7)
        self.assertEqual(len(result["private_identity_hashes"]), 9)
        self.assertNotIn("private owned fixture", json.dumps(result))
        self.assertTrue(all("SELECT" in call.args[1] for call in reads.call_args_list))
        old = result["private_identity_hashes"]["jwt"]
        (self.root / "jwt").write_bytes(b"changed")
        self.assertNotEqual(self.capture()[0]["private_identity_hashes"]["jwt"], old)
        for volumes in (
            self.resources["volumes"][:-1],
            self.resources["volumes"] + [self.resources["volumes"][0]],
            [{**volume, "CreatedAt": None} for volume in self.resources["volumes"]],
        ):
            with (
                self.subTest(volumes=volumes),
                self.assertRaises(snapshot.SnapshotError),
            ):
                self.capture(volumes=volumes)

    def test_invalid_uuid_or_runtime_configuration_refused(self):
        for database_uuid in ("-" * 36, DATABASE.upper(), "not-a-uuid"):
            with (
                self.subTest(uuid=database_uuid),
                self.assertRaises(snapshot.SnapshotError),
            ):
                self.capture(database_uuid=database_uuid)
        with self.assertRaises(snapshot.SnapshotError):
            self.capture(runtime={"bucket": "foreign"})

    def test_sql_reads_are_explicitly_read_only_and_errors_do_not_echo_output(self):
        with patch.object(snapshot, "output", return_value=" 42\n") as invoke:
            self.assertEqual(snapshot.database_read("1" * 64, "SELECT 42"), "42")
        self.assertEqual(
            invoke.call_args.args[0][-1], "BEGIN READ ONLY; SELECT 42; ROLLBACK;"
        )
        with (
            patch.object(
                snapshot.subprocess,
                "run",
                return_value=Mock(returncode=1, stdout="SECRET", stderr="SECRET"),
            ),
            self.assertRaises(snapshot.SnapshotError) as error,
        ):
            snapshot.output(["docker", "exec", "owned"])
        self.assertNotIn("SECRET", str(error.exception))

    def test_readiness_waits_for_exact_marker_without_mutating_or_ignoring_new_objects(
        self,
    ):
        missing = {
            "bucket": {
                "objects": 12,
                "owner_marker": {"present": False, "matches_database": False},
            }
        }
        ready = {"bucket": self.bucket}
        with (
            patch.object(snapshot, "capture", side_effect=[missing, ready]) as capture,
            patch.object(snapshot.time, "sleep") as sleep,
        ):
            self.assertEqual(snapshot.ready_baseline("owned", OWNER), ready)
        self.assertEqual(capture.call_count, 2)
        sleep.assert_called_once_with(1)
        foreign = copy.deepcopy(ready)
        foreign["bucket"]["owner_marker"]["matches_database"] = False
        with (
            patch.object(snapshot, "capture", return_value=foreign),
            patch.object(snapshot.time, "sleep") as sleep,
        ):
            with self.assertRaises(snapshot.SnapshotError):
                snapshot.ready_baseline("owned", OWNER)
            sleep.assert_not_called()
        extra = copy.deepcopy(ready)
        extra["bucket"]["objects"] = 14
        with (
            patch.object(snapshot, "capture", return_value=extra),
            patch.object(snapshot.time, "monotonic", side_effect=[0, 301]),
            self.assertRaises(snapshot.SnapshotError),
        ):
            snapshot.ready_baseline("owned", OWNER)

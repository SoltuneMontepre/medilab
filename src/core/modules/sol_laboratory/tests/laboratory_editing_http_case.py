import hashlib
import os
import subprocess
import sys
import tempfile
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import requests

from odoo.tools import config

from .editing_service import PUBLIC_URL, SECRET, LocalEditingService, callback
from .laboratory_bucket_case import LaboratoryBucketTools, closed_port
from .laboratory_bucket_proxy import LaboratoryBucketProxy
from .laboratory_editing_concurrency_case import LaboratoryEditingConcurrencyCase
from odoo.addons.sol_laboratory.constants.laboratory_bucket import ADDRESS_VARIABLE, NAME_VARIABLE
from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    CALLBACK_DOCUMENT_PATH,
    CALLBACK_DOCUMENT_URI,
    CALLBACK_PREFIX,
    INTERNAL_URL_VARIABLE,
    JWT_HEADER,
    JWT_SECRET_VARIABLE,
    PUBLIC_URL_VARIABLE,
)
from odoo.addons.sol_laboratory.constants.laboratory_reconciliation import MARKER_KEY
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_LABORATORY_CONTENT
from odoo.addons.sol_laboratory.services import laboratory_bucket, openapi_document

CALLBACK_BUCKET = "laboratory-files-callback-http"


class LaboratoryEditingHttpCase(LaboratoryBucketTools, LaboratoryEditingConcurrencyCase):
    """A normal Odoo HTTP process, without HttpCase's shared TestCursor. Fixtures and assertions use independent
    committed transactions in the guarded test database. The document source is a fixture, not Document Server."""

    bucket_name = CALLBACK_BUCKET
    extra_log_handlers = ()

    @classmethod
    def server_environment(cls):
        return {}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enterClassContext(patch.dict(os.environ, {NAME_VARIABLE: cls.bucket_name}))
        cls.bucket_owner = cls.env[MODEL_LABORATORY_CONTENT]._database_uuid()
        owner = laboratory_bucket.read_text(MARKER_KEY)
        if owner is not None and owner.strip() != cls.bucket_owner:
            raise AssertionError("The callback test bucket belongs to another database; review the interrupted run.")
        laboratory_bucket.write_text(MARKER_KEY, cls.bucket_owner)
        cls.addClassCleanup(cls.remove_bucket_marker)
        bucket = laboratory_bucket.settings()
        if bucket is None:
            raise AssertionError("The callback HTTP tests require the local Garage bucket.")
        cls.bucket_proxy = LaboratoryBucketProxy(SimpleNamespace(addCleanup=cls.addClassCleanup), bucket.address)
        cls.source = LocalEditingService(SimpleNamespace(addCleanup=cls.addClassCleanup))
        cls.server_log = cls.enterClassContext(tempfile.TemporaryFile(mode="w+b"))
        cls.http_url = f"http://127.0.0.1:{closed_port()}"
        command = [
            sys.executable,
            "-m",
            "odoo",
            "-d",
            cls.registry.db_name,
            "--http-interface=127.0.0.1",
            f"--http-port={cls.http_url.rsplit(':', 1)[1]}",
            "--workers=0",
            "--max-cron-threads=0",
            "--log-level=info",
            "--log-handler=odoo.http.server:DEBUG",
            "--log-handler=urllib3.connectionpool:DEBUG",
            *(f"--log-handler={handler}" for handler in cls.extra_log_handlers),
        ]
        for option in ("db_host", "db_port", "db_user", "db_password", "data_dir", "addons_path"):
            if value := config[option]:
                command.extend(
                    [
                        ("--" + option.replace("_", "-") if option in ("data_dir", "addons_path") else "--" + option),
                        ",".join(map(str, value)) if isinstance(value, (list, tuple)) else str(value),
                    ]
                )
        cls.http_server = subprocess.Popen(
            command,
            stdout=cls.server_log,
            stderr=subprocess.STDOUT,
            env={
                **os.environ,
                JWT_SECRET_VARIABLE: SECRET,
                INTERNAL_URL_VARIABLE: cls.source.url,
                PUBLIC_URL_VARIABLE: PUBLIC_URL,
                ADDRESS_VARIABLE: cls.bucket_proxy.url,
                **cls.server_environment(),
            },
        )
        cls.addClassCleanup(cls.stop_server)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if cls.http_server.poll() is not None:
                cls.server_log.seek(0)
                raise AssertionError(cls.server_log.read().decode(errors="replace"))
            try:
                if requests.get(f"{cls.http_url}/web/health", timeout=1).status_code == 200:
                    return
            except requests.ConnectionError:
                time.sleep(0.2)
                continue
            time.sleep(0.2)
        raise AssertionError("The independent Odoo HTTP process did not start.")

    @classmethod
    def remove_bucket_marker(cls):
        owner = laboratory_bucket.read_text(MARKER_KEY)
        if owner is not None and owner.strip() == cls.bucket_owner:
            laboratory_bucket.delete(MARKER_KEY)

    @classmethod
    def stop_server(cls):
        cls.http_server.terminate()
        try:
            cls.http_server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.http_server.kill()
            cls.http_server.wait(timeout=10)

    def setUp(self):
        super().setUp()
        self.source.before_get = None
        self.bucket_proxy.failure = 0
        self.source.asked.clear()
        self.content = f"Kết quả sửa trực tuyến {uuid.uuid4()}".encode()
        self.saved_sha = hashlib.sha256(self.content).hexdigest()
        self.saved_path = f"/cache/{uuid.uuid4()}/output.xlsx"
        self.source.answer(self.saved_path, self.content)
        self.objects_before = {key for key, _size, _date in laboratory_bucket.objects()}
        self.addCleanup(self.remove_saved_bytes)
        self.session_id, self.document_key, self.callback_token, self.editor_id = self.committed(self.prepare_session)

    def prepare_session(self, env):
        session = self.open(env)
        return session.id, session.document_key, session._callback_token(), env.ref("base.user_admin").id

    def remove_saved_bytes(self):
        # Rollbacks leave no content row. Delete only this test's unique bytes, never another shard's objects.
        for key in self.owned_saved_objects():
            laboratory_bucket.delete(key)

    def owned_saved_objects(self):
        keys = []
        for key, size, _date in laboratory_bucket.objects():
            if key not in self.objects_before and size == len(self.content):
                with laboratory_bucket.read(key) as chunks:
                    digest = hashlib.sha256(b"".join(chunks)).hexdigest()
                if digest == self.saved_sha:
                    keys.append(key)
        return keys

    def fields(self, status=2, **values):
        return {
            "key": self.document_key,
            "status": status,
            "url": f"{PUBLIC_URL}{self.saved_path}",
            "users": [str(self.editor_id)],
            **values,
        }

    def send(self, fields=None, *, token=None, header=True, body_token=True, **options):
        body, signed = callback(fields if fields is not None else self.fields(), header=header, body_token=body_token)
        headers = options.pop("headers", {})
        if signed:
            headers[JWT_HEADER] = signed
        return requests.post(
            self.http_url + CALLBACK_PREFIX + (token or self.callback_token),
            json=body,
            headers=headers,
            timeout=90,
            allow_redirects=False,
            **options,
        )

    def assertAnswer(self, response, status):
        self.assertEqual(response.status_code, status, response.text[:200])
        self.assertEqual(response.json(), {"error": 0 if status == 200 else 1})
        self.assertIn("application/json", response.headers["Content-Type"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertNotIn("Set-Cookie", response.headers)
        answer = openapi_document.documented_answer(
            "receiveEditingCallback", status, document_path=CALLBACK_DOCUMENT_PATH
        )
        self.assertIsNotNone(answer, "The callback returned an undocumented status.")
        for name in openapi_document.required_headers(answer, document_path=CALLBACK_DOCUMENT_PATH):
            self.assertIn(name, response.headers)
        pointer = openapi_document.answer_pointer(
            "receiveEditingCallback", status, document_path=CALLBACK_DOCUMENT_PATH
        )
        self.assertIsNotNone(pointer)
        self.assertIsNone(
            openapi_document.schema_error(
                pointer,
                response.json(),
                document_path=CALLBACK_DOCUMENT_PATH,
                document_uri=CALLBACK_DOCUMENT_URI,
            )
        )

    def entries(self):
        return self.committed(
            lambda env: env[MODEL_AUDIT_ENTRY].search_read(
                [("document_model", "=", "medilab.laboratory.editing.session"), ("document_id", "=", self.session_id)],
                ["source", "user_id", "action"],
                order="id",
            )
        )

    def saved_objects(self):
        return self.committed(
            lambda env: env[MODEL_LABORATORY_CONTENT].search_read(
                [("sha256", "=", self.saved_sha)], ["object_key", "state"]
            )
        )

    def server_messages(self):
        return os.pread(self.server_log.fileno(), os.fstat(self.server_log.fileno()).st_size, 0).decode(
            errors="replace"
        )

    def attempt_trigger(self, failures, code="40001", delay=0, deferred=False):
        """A real PostgreSQL failure after the HTTP save wrote its object. Sequences survive rollback, exposing how
        many attempts Odoo made. All trigger objects belong to this guarded test database and are removed."""

        def install(env):
            env.cr.execute("CREATE SEQUENCE medilab_callback_http_attempt")
            env.cr.execute(
                """
                CREATE FUNCTION medilab_callback_http_failure() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.id = %s AND NEW.status = OLD.status AND nextval('medilab_callback_http_attempt') <= %s THEN
                        PERFORM pg_sleep(%s);
                        RAISE EXCEPTION 'Callback HTTP test failure' USING ERRCODE = %s;
                    END IF;
                    RETURN NEW;
                END $$
            """,
                [self.session_id, failures, delay, code],
            )
            if deferred:
                env.cr.execute("""CREATE CONSTRAINT TRIGGER medilab_callback_http_failure AFTER UPDATE
                    ON medilab_laboratory_editing_session DEFERRABLE INITIALLY DEFERRED
                    FOR EACH ROW EXECUTE FUNCTION medilab_callback_http_failure()""")
            else:
                env.cr.execute("""CREATE TRIGGER medilab_callback_http_failure BEFORE UPDATE
                    ON medilab_laboratory_editing_session FOR EACH ROW EXECUTE FUNCTION medilab_callback_http_failure()""")

        self.committed(install)
        self.addCleanup(self.committed, self.remove_trigger)

    @staticmethod
    def remove_trigger(env):
        env.cr.execute("DROP TRIGGER medilab_callback_http_failure ON medilab_laboratory_editing_session")
        env.cr.execute("DROP FUNCTION medilab_callback_http_failure()")
        env.cr.execute("DROP SEQUENCE medilab_callback_http_attempt")

    def attempts(self):
        def read(env):
            env.cr.execute("SELECT last_value FROM medilab_callback_http_attempt")
            return env.cr.fetchone()[0]

        return self.committed(read)

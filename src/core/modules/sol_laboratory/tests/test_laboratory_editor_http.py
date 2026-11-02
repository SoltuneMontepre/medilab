import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import requests
from lxml import html

from odoo import fields
from odoo.tests import tagged

from .laboratory_editing_http_case import LaboratoryEditingHttpCase
from odoo.addons.sol_laboratory.constants.laboratory_bucket import PUBLIC_ADDRESS_VARIABLE
from odoo.addons.sol_laboratory.constants.laboratory_editing import EXPIRED, PUBLIC_URL_VARIABLE
from odoo.addons.sol_laboratory.services.laboratory_editor_page import CALLBACK_ORIGIN_VARIABLE
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

ADMIN_PASSWORD = "admin"


@tagged("post_install", "-at_install")
class TestLaboratoryEditorHttp(LaboratoryEditingHttpCase):
    """Normal HTTP login and page requests; assertions read independently committed transactions."""

    bucket_name = "laboratory-files-editor-http"
    extra_log_handlers = ("botocore.auth:DEBUG",)

    @classmethod
    def server_environment(cls):
        return {
            CALLBACK_ORIGIN_VARIABLE: cls.http_url,
            PUBLIC_URL_VARIABLE: cls.source.url,
            PUBLIC_ADDRESS_VARIABLE: cls.bucket_proxy.url,
        }

    def prepare_session(self, env):
        admin = env.ref("base.user_admin")
        return 0, "", "", admin.id

    def setUp(self):
        super().setUp()
        self.source.answer("/healthcheck", b"true")
        self.path = f"/medilab/laboratory-files/{self.file_id}/edit"
        self.client = self.login()

    def login(self: LaboratoryEditingHttpCase):
        client = requests.Session()
        self.addCleanup(client.close)
        response = client.get(self.http_url + "/web/login", timeout=30)
        token_input = html.fromstring(response.content).find(".//input[@name='csrf_token']")
        if token_input is None:
            self.fail("The login page did not provide its CSRF token.")
        token = token_input.get("value")
        response = client.post(
            self.http_url + "/web/login",
            data={"login": "admin", "password": ADMIN_PASSWORD, "csrf_token": token, "redirect": self.path},
            allow_redirects=False,
            timeout=30,
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], self.path)
        return client

    def get_page(self, client=None, *, status=200, **options):
        response = (client or self.client).get(self.http_url + self.path, timeout=60, allow_redirects=False, **options)
        self.assertEqual(response.status_code, status, response.text[:200])
        if status != 200:
            return {}
        return json.loads(
            assert_instance(html.fromstring(response.content), html.HtmlElement)
            .get_element_by_id("laboratory-editor")
            .get("data-editor-config")
        )

    def identity(self):
        return self.committed(
            lambda env: [
                (row.id, row.document_key, row.base_version_id.id, row.status)
                for row in self.file(env).editing_session_ids
            ]
        )

    def test_non_ascii_file_ids_are_refused_before_opening_a_session(self):
        for digits in ("٠١٢٣٤٥٦٧٨٩", "０１２３４５６７８９"):
            identifier = str(self.file_id).translate(str.maketrans("0123456789", digits))
            response = self.client.get(
                f"{self.http_url}/medilab/laboratory-files/{identifier}/edit", timeout=30, allow_redirects=False
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(self.identity(), [])

    def test_login_open_and_reentry_commit_one_session(self):
        first = self.get_page()
        identity = self.identity()
        self.assertEqual(len(identity), 1)
        second = self.get_page()
        self.assertEqual(first["document"]["key"], second["document"]["key"])
        self.assertEqual(self.identity(), identity)

    def test_concurrent_opens_retry_and_commit_one_session(self):
        other = self.login()
        barrier = threading.Barrier(2)
        calls = []
        lock = threading.Lock()

        def health(path):
            if path == "/healthcheck":
                with lock:
                    calls.append(path)
                    wait = len(calls) <= 2
                if wait:
                    barrier.wait(timeout=10)

        self.source.before_get = health
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(self.get_page, (self.client, other)))
        self.assertEqual(responses[0]["document"]["key"], responses[1]["document"]["key"])
        self.assertEqual(len(self.identity()), 1)

    def test_service_failure_leaves_no_committed_session_and_retry_works(self):
        self.source.answer("/healthcheck", b"false")
        self.get_page(status=503)
        self.assertEqual(self.identity(), [])
        self.source.answer("/healthcheck", b"true")
        self.get_page()
        self.assertEqual(len(self.identity()), 1)

    def test_explicit_idle_reentry_expires_old_session_and_commits_new_key(self):
        first = self.get_page()
        self.committed(
            lambda env: self.session(env).write({"last_activity_at": fields.Datetime.now() - timedelta(hours=13)})
        )
        second = self.get_page()
        self.assertNotEqual(first["document"]["key"], second["document"]["key"])
        identities = self.identity()
        self.assertEqual(len(identities), 2)
        self.assertIn(EXPIRED, [identity[3] for identity in identities])

    def test_logout_requires_login_again_and_retains_existing_session(self):
        self.get_page()
        identity = self.identity()
        login_page = self.client.get(self.http_url + "/web/login", timeout=30)
        token_input = html.fromstring(login_page.content).find(".//input[@name='csrf_token']")
        if token_input is None:
            self.fail("The login page did not provide its CSRF token.")
        response = self.client.post(
            self.http_url + "/web/session/logout",
            data={"csrf_token": token_input.get("value")},
            allow_redirects=False,
            timeout=30,
        )
        self.assertEqual(response.status_code, 303)
        self.get_page(status=303)
        self.assertEqual(self.identity(), identity)

    def test_page_transport_logs_do_not_include_configuration_credentials(self):
        config = self.get_page()
        logs = self.server_messages()
        self.assertNotRegex(logs, r"X-Amz-(?:Signature|Credential|Algorithm)")
        for secret in (
            config["token"],
            config["document"]["url"],
            config["editorConfig"]["callbackUrl"].rsplit("/", 1)[1],
        ):
            self.assertFalse(secret in logs, "Editor configuration credentials were logged.")

    def test_untrusted_host_does_not_supply_callback_origin(self):
        config = self.get_page(
            headers={
                "Host": "attacker.example",
                "X-Forwarded-Host": "attacker.example",
                "Cookie": f"session_id={self.client.cookies.get('session_id')}",
            }
        )
        self.assertTrue(
            config["editorConfig"]["callbackUrl"].startswith(self.http_url + "/medilab/laboratory-files/callback/")
        )

import re
from contextlib import contextmanager
from urllib.parse import urlsplit

from odoo.tests import HttpCase

from .laboratory_files_case import PASSWORD, LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_api import API_PREFIX, ERROR_STATUSES
from odoo.addons.sol_laboratory.services import openapi_document

# The browser headers with which Odoo's bearer authentication takes a signed-in session in place of a key.
BROWSER_NAVIGATION = {
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}


class LaboratoryApiCase(HttpCase, LaboratoryFilesCase):
    """The laboratory files API called through real HTTP requests. Every answer is checked against the OpenAPI document,
    so the tests of each route are its contract tests."""

    def setUp(self):
        super().setUp()
        # Odoo's login cooldown counts failures per address in the registry, which every test of the process shares.
        self.clear_login_cooldown()
        self.addCleanup(self.clear_login_cooldown)

    def clear_login_cooldown(self):
        getattr(self.registry, "_login_failures", {}).clear()

    def api(self, method, path, body=None, key=None, headers=None, data=None):
        """Call the API at the path under /medilab/api/v1 and check the answer against the document."""
        headers = dict(headers or {})
        if key:
            headers["Authorization"] = f"Bearer {key}"
        response = self.url_open(
            API_PREFIX + path, data=data, json=body, headers=headers, method=method, allow_redirects=False
        )
        self.assertMatchesDocument(method, path, response)
        return response

    @contextmanager
    def expected_http_warnings(self, *messages):
        with self.assertLogs("odoo.http", level="WARNING") as logged:
            yield
        records = [(record.levelname, record.getMessage()) for record in logged.records]
        if all(isinstance(message, str) for message in messages):
            self.assertEqual(records, [("WARNING", message) for message in messages])
            return
        self.assertEqual(len(records), len(messages))
        for (level, actual), expected in zip(records, messages, strict=True):
            self.assertEqual(level, "WARNING")
            if isinstance(expected, str):
                self.assertEqual(actual, expected)
            else:
                self.assertIsNotNone(expected.fullmatch(actual), actual)

    @staticmethod
    def timestamped_http_warning(prefix):
        return re.compile(re.escape(prefix) + r"\d{2}/\d{2}/\d{4} \d{2}:\d{2} [AP]M\.")

    def api_sign_in(self, user, client_uid, password=PASSWORD, name="HPLC-PC", platform="windows"):
        body = {"login": user.login, "password": password, "client_uid": client_uid, "name": name, "platform": platform}
        return self.api("POST", "/sign-in", body)

    def signed_in_key(self, user, client_uid, **values):
        response = self.api_sign_in(user, client_uid, **values)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["key"]

    def assertApiRefused(self, code, response):
        self.assertEqual(response.headers.get("Content-Type"), "application/json; charset=utf-8", response.text)
        self.assertEqual(response.json()["error"]["code"], code, response.text)
        self.assertEqual(response.status_code, ERROR_STATUSES[code])

    def assertMatchesDocument(self, method, path, response):
        """The answer is one the document gives for the request: a documented status, its required headers and a body
        that matches its schema, and for a refusal the status of its code. A path or method the document does not have
        is refused as not found or as a method the route does not take."""
        operation, path_known = self.operation_of(method, path)
        status = response.status_code
        if operation is None:
            self.assertEqual(status, 405 if path_known else 404, response.text)
            self.assertIsNone(openapi_document.schema_error(openapi_document.ERROR_SCHEMA, response.json()))
            if path_known:
                self.assertIn("Allow", response.headers)
            return
        answer = openapi_document.documented_answer(operation, status)
        self.assertIsNotNone(answer, f"{method} {path} answered {status}, which the document does not give")
        for header in openapi_document.required_headers(answer):
            self.assertIn(header, response.headers, f"{method} {path} answered {status} without {header}")
        pointer = openapi_document.answer_pointer(operation, status)
        if pointer is None:
            self.assertFalse(response.content, f"{method} {path} answered {status} with a body")
            return
        body = response.json()
        error = openapi_document.schema_error(pointer, body)
        self.assertIsNone(error, f"{method} {path} answered {status} with {body}: {error}")
        if "error" in body:
            self.assertEqual(ERROR_STATUSES[body["error"]["code"]], status)

    @staticmethod
    def operation_of(method, path):
        """The operationId the document gives the request, and whether the document has its path at all."""
        path = urlsplit(path).path
        path_known = False
        for operation, (operation_method, template, _operation) in openapi_document.operations().items():
            if re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", template), path):
                path_known = True
                if operation_method == method.upper():
                    return operation, True
        return None, path_known

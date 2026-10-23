from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_api_case import LaboratoryApiCase
from .laboratory_files_case import PASSWORD
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_ALLOWED,
    NOT_FOUND,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError

SIGN_IN = {"login": "lab.tester", "password": PASSWORD, "client_uid": "installation", "name": "HPLC-PC"}


@tagged("post_install", "-at_install")
class TestLaboratoryApiErrors(LaboratoryApiCase):
    """Every refusal of the API answers its code and message with the status of its code, and only what the document
    describes reaches a route."""

    def test_a_request_that_does_not_match_the_document_is_refused(self):
        key = self.signed_in_key(self.tester, "installation")
        refused = (
            ("a body that is not JSON", "POST", "/sign-in", {"data": "{not json", "headers": self.json_type()}),
            ("a body of another type", "POST", "/sign-in", {"data": "login=lab.tester"}),
            ("a missing field", "POST", "/sign-in", {"body": SIGN_IN}),
            ("a field the API does not have", "POST", "/sign-in", {"body": {**SIGN_IN, "platform": "linux", "x": 1}}),
            ("a value of the wrong kind", "POST", "/sign-in", {"body": {**SIGN_IN, "platform": "macos"}}),
            ("a parameter the route does not take", "GET", "/devices?folder=1", {"key": key}),
            ("a body on a route without one", "POST", "/sign-out", {"key": key, "body": {"device": 1}}),
        )
        for reason, method, path, request in refused:
            with self.subTest(reason):
                self.assertApiRefused(INVALID_REQUEST, self.api(method, path, **request))
        self.assertEqual(self.api("GET", "/devices", key=key).status_code, 200)

    def test_a_path_the_api_does_not_have_is_not_found(self):
        self.assertApiRefused(NOT_FOUND, self.api("GET", "/samples"))

    def test_a_method_a_route_does_not_take_is_refused_with_the_methods_it_takes(self):
        for method in ("DELETE", "PUT", "OPTIONS"):
            with self.subTest(method=method):
                response = self.api(method, "/sign-in")

                self.assertApiRefused(METHOD_NOT_ALLOWED, response)
                self.assertEqual(response.headers["Allow"], "POST")

    def test_an_unexpected_error_answers_an_id_the_server_logged_it_under_and_no_detail(self):
        key = self.signed_in_key(self.tester, "installation")
        devices = type(self.env[MODEL_LABORATORY_DEVICE])

        def fail(_device, _current):
            raise RuntimeError("secret detail of the server")

        self.patch(devices, "_laboratory_api_values", fail)
        # Odoo logs the exception too, as it does every exception of a request.
        with (
            self.assertLogs("odoo.addons.sol_laboratory.services.laboratory_api", "ERROR") as logged,
            mute_logger("odoo.http"),
        ):
            response = self.api("GET", "/devices", key=key)

        self.assertApiRefused(INTERNAL_ERROR, response)
        error = response.json()["error"]
        self.assertNotIn("secret", error["message"])
        self.assertIn(error["id"], logged.output[0])
        self.assertIn("secret detail of the server", "\n".join(logged.output))

    def test_a_record_the_person_may_not_read_is_not_found(self):
        key = self.signed_in_key(self.tester, "installation")
        devices = type(self.env[MODEL_LABORATORY_DEVICE])

        def unreadable(_device, _current):
            raise AccessError("You are not allowed to read this computer.")

        self.patch(devices, "_laboratory_api_values", unreadable)
        response = self.api("GET", "/devices", key=key)

        self.assertApiRefused(NOT_FOUND, response)
        self.assertNotIn("not allowed", response.json()["error"]["message"])

    def test_a_refused_request_commits_nothing_it_did_before_the_refusal(self):
        key = self.signed_in_key(self.tester, "first-installation")
        self.signed_in_key(self.tester, "second-installation")
        second = self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", "second-installation")])
        devices = type(self.env[MODEL_LABORATORY_DEVICE])

        def refuse(_device, _current):
            raise LaboratoryFileError(NOT_FOUND, "Refused after revoking.")

        self.patch(devices, "_laboratory_api_values", refuse)
        response = self.api("POST", f"/devices/{second.id}/revoke", key=key)

        self.assertApiRefused(NOT_FOUND, response)
        self.assertEqual(second.status, "signed_in")

    @staticmethod
    def json_type():
        return {"Content-Type": "application/json"}

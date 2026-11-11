import re
from types import SimpleNamespace

from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from odoo.addons.sol_laboratory.constants.laboratory_api import API_PREFIX, ERROR_STATUSES
from odoo.addons.sol_laboratory.constants.laboratory_files import DEVICE_KEY_SCOPE
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_HTTP
from odoo.addons.sol_laboratory.services import openapi_document
from odoo.addons.sol_laboratory.services.laboratory_api import is_api_path
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

# The routes that cannot take a computer's key: signing in, which gives it, and the health checks.
WITHOUT_KEY = {("POST", "/sign-in"): "public", ("GET", "/health"): "none", ("GET", "/ready"): "none"}


@tagged("post_install", "-at_install")
class TestLaboratoryApiRoutes(LaboratoryApiCase):
    def api_routes(self):
        """Each route under the API's path, by method and path as the document writes it, with its routing."""
        routes = {}
        for rule in self.env[MODEL_IR_HTTP].routing_map().iter_rules():
            if not rule.rule.startswith(API_PREFIX + "/") or not is_api_path(rule.rule):
                continue
            path = re.sub(r"<(?:[^:<>]+:)?([^:<>]+)>", r"{\1}", rule.rule.removeprefix(API_PREFIX))
            for method in assert_instance(getattr(rule.endpoint, "routing"), dict)["methods"]:
                routes[method, path] = assert_instance(getattr(rule.endpoint, "routing"), dict)
        return routes

    def test_every_route_takes_only_a_computers_key_without_csrf_or_session(self):
        routes = self.api_routes()

        self.assertTrue(routes)
        for (method, path), routing in routes.items():
            with self.subTest(method=method, path=path):
                self.assertEqual(routing["type"], "http")
                self.assertIs(routing["csrf"], False)
                self.assertIs(routing["save_session"], False)
                self.assertEqual(routing["methods"], [method])
                if (method, path) in WITHOUT_KEY:
                    self.assertEqual(routing["auth"], WITHOUT_KEY[method, path])
                else:
                    self.assertEqual(routing["auth"], "bearer")
                    self.assertEqual(routing["bearer_scope"], DEVICE_KEY_SCOPE)
                    self.assertIs(routing["readonly"], False)

    def test_the_routes_are_the_operations_of_the_document(self):
        documented = {(method, path) for method, path, _operation in openapi_document.operations().values()}

        self.assertEqual(set(self.api_routes()), documented)

    def test_the_document_gives_every_code_the_status_of_the_api(self):
        document = openapi_document.document()
        codes = document["components"]["schemas"]["Error"]["properties"]["error"]["properties"]["code"]["enum"]
        statuses = {}
        for _method, _path, operation in openapi_document.operations().values():
            for status, answer in operation["responses"].items():
                if "$ref" not in answer:
                    continue
                schema = document["components"]["responses"][answer["$ref"].rsplit("/", 1)[1]]["content"]
                code = schema["application/json"]["schema"]["allOf"][1]["properties"]["error"]["properties"]["code"]
                for each in code["enum"]:
                    statuses.setdefault(each, set()).add(int(status))

        self.assertEqual(sorted(codes), sorted(ERROR_STATUSES))
        for code, used in statuses.items():
            with self.subTest(code=code):
                self.assertEqual(used, {ERROR_STATUSES[code]})

    def test_an_answer_the_document_does_not_give_fails_its_test(self):
        def answer(status, body, headers=None):
            return SimpleNamespace(
                status_code=status, json=lambda: body, content=b"{}", headers=headers or {}, text=str(body)
            )

        wrong = (
            ("an undocumented status", answer(418, {"status": "pass"})),
            ("a field the schema does not have", answer(200, {"status": "pass", "uptime": 3})),
            ("a code of another status", answer(500, {"error": {"code": "not_found", "message": "", "id": "x"}})),
        )
        for reason, response in wrong:
            with self.subTest(reason), self.assertRaises(AssertionError):
                self.assertMatchesDocument("GET", "/health", response)
        with self.assertRaises(AssertionError):
            refused = {"error": {"code": "method_not_allowed", "message": "This route does not take the method."}}
            self.assertMatchesDocument("DELETE", "/health", answer(405, refused))

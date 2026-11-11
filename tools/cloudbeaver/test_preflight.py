"""Protected preflight inventory must never mistake setup-mode anonymous access for account evidence."""

import copy
import io
import json
import unittest
from unittest.mock import Mock, patch

from preflight_inventory import inventory


class TestPreflight(unittest.TestCase):
    def inspect(self, data, errors=None):
        opener = Mock()
        response = io.BytesIO(json.dumps({"data": data, "errors": errors}).encode())
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with (
            patch("preflight_inventory.http.cookiejar.MozillaCookieJar.load"),
            patch("preflight_inventory.urllib.request.build_opener", return_value=opener),
        ):
            result = inventory("approved-session", "operator")
        request = opener.open.call_args.args[0]
        query = json.loads(request.data)["query"]
        self.assertNotIn("authLogin", query)
        self.assertNotIn("mutation", query)
        self.assertNotIn("password", query.lower())
        return result

    def data(self):
        return {
            "serverConfig": {"configurationMode": False},
            "activeUser": {"userId": "operator", "isAnonymous": False},
            "listUsers": [{"userId": "operator", "enabled": True, "authRole": "admin", "grantedTeams": ["admin"]}],
            "listTeams": [{"teamId": "admin"}],
            "userConnections": [{"id": "retained", "name": "DO-NOT-PRINT-THIS-CONNECTION-NAME"}],
        }

    def test_anonymous_setup_session_is_not_account_evidence(self):
        for active in (None, {"userId": "@anonymous@", "isAnonymous": True}, {"userId": "operator"}):
            data = self.data()
            data["serverConfig"]["configurationMode"] = True
            data["activeUser"] = active
            with self.subTest(active=active), self.assertRaises(RuntimeError):
                self.inspect(data)

    def test_disabled_or_missing_persistent_identity_is_not_verified(self):
        for users in ([], [{"userId": "operator", "enabled": False}]):
            data = self.data()
            data["listUsers"] = users
            with self.subTest(users=users), self.assertRaises(RuntimeError):
                self.inspect(data)

    def test_inventory_requires_an_authenticated_persistent_account(self):
        data = self.data()
        result = self.inspect(copy.deepcopy(data))
        self.assertTrue(result["verified"])
        self.assertTrue(result["active_identifier_matches_secret"])
        self.assertFalse(result["configuration_mode"])
        self.assertEqual(result["users"], 1)
        self.assertNotIn("DO-NOT-PRINT", json.dumps(result))
        self.assertNotIn("operator", json.dumps(result))
        data["serverConfig"]["configurationMode"] = True
        self.assertTrue(self.inspect(data)["configuration_mode"])

    def test_graphql_errors_fail_closed(self):
        with self.assertRaises(RuntimeError):
            self.inspect(self.data(), [{"message": "private-error-canary"}])


if __name__ == "__main__":
    unittest.main()

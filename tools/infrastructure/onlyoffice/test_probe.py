"""The monitor validates TLS and reports health without disclosing service failures."""

import importlib.util
import ssl
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

SOURCE = Path(__file__).resolve().parents[3] / "infra/cluster/onlyoffice-monitor/probe.py"
SPEC = importlib.util.spec_from_file_location("onlyoffice_monitor_probe", SOURCE)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class TestProbe(unittest.TestCase):
    def answer(self, status, content):
        response = MagicMock()
        response.status = status
        response.read.return_value = content
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        return opener

    def test_exact_health_response_uses_verified_tls_without_proxies_or_redirects(self):
        context = ssl.create_default_context()
        opener = self.answer(200, b"true\n")
        with (
            patch.object(probe.ssl, "create_default_context", return_value=context) as create,
            patch.object(probe.urllib.request, "build_opener", return_value=opener) as build,
        ):
            self.assertTrue(probe.healthy())

        create.assert_called_once_with(cafile="/run/onlyoffice-ca/ca.crt")
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        proxy, redirect, tls = build.call_args.args
        self.assertEqual(proxy.proxies, {})
        self.assertIsNone(redirect.redirect_request(None, None, 302, "", {}, "https://other.example"))
        self.assertIs(tls._context, context)
        opener.open.assert_called_once_with(probe.URL, timeout=5)

    def test_partial_health_body_and_other_success_codes_are_not_ready(self):
        for status, content in ((200, b"true followed by failure"), (200, b"false"), (204, b"true")):
            with (
                self.subTest(status=status, content=content),
                patch.object(probe.ssl, "create_default_context"),
                patch.object(probe.urllib.request, "build_opener", return_value=self.answer(status, content)),
            ):
                self.assertFalse(probe.healthy())

    def test_transport_failure_and_refused_redirect_are_not_ready(self):
        for error in (OSError("private details"), urllib.error.URLError("private URL")):
            opener = MagicMock()
            opener.open.side_effect = error
            with (
                self.subTest(error=type(error)),
                patch.object(probe.ssl, "create_default_context"),
                patch.object(probe.urllib.request, "build_opener", return_value=opener),
            ):
                self.assertFalse(probe.healthy())


if __name__ == "__main__":
    unittest.main()

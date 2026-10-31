"""Check verification failure reasons and cleanup ownership without contacting user services."""

import io
import os
import sys
import unittest
import zipfile
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import jwt
from botocore.exceptions import ClientError


class TransportFailure(Exception):
    pass


# requests is provided by the Odoo image. Host contracts inject its transport boundary deliberately.
transport = ModuleType("requests")
transport.Session = lambda: None
transport.RequestException = TransportFailure
transport.ConnectionError = TransportFailure
with patch.dict(sys.modules, {"requests": transport}):
    import verify as verifier

MARKER = "a" * 32
BUCKET = "laboratory-files"
KEY = f"onlyoffice-setup/{MARKER}/input.docx"
ENVIRONMENT = {
    "ONLYOFFICE_INTERNAL_URL": "https://onlyoffice-gateway:9443",
    "ONLYOFFICE_PUBLIC_URL": "http://localhost:29843",
    "ONLYOFFICE_CALLBACK_ORIGIN": "https://onlyoffice-gateway:7443",
    "ONLYOFFICE_JWT_SECRET": "local-contract-only-signing-material",
    "REQUESTS_CA_BUNDLE": "/run/onlyoffice-trust/bundle.crt",
    "BUCKET_LABORATORY_NAME": BUCKET,
    "BUCKET_LABORATORY_REGION": "garage",
    "BUCKET_LABORATORY_ADDRESS": "http://garage:3900",
    "BUCKET_LABORATORY_PUBLIC_ADDRESS": "http://localhost:23900",
    "BUCKET_LABORATORY_ACCESS_KEY": "local-contract-access",
    "BUCKET_LABORATORY_SECRET_KEY": "local-contract-secret",
}


def response(status=200, *, value=None, text="", content=b""):
    return SimpleNamespace(
        status_code=status, text=text, content=content, json=lambda: value
    )


class Storage:
    exceptions = SimpleNamespace(ClientError=ClientError)

    def __init__(self):
        self.calls = []
        self.objects = {}
        self.upload_error = None
        self.delete_error = None
        self.head_status = 404

    def put_object(self, *, Bucket, Key, Body):
        self.calls.append(("put", Bucket, Key))
        if self.upload_error:
            raise self.upload_error
        self.objects[Bucket, Key] = Body

    def delete_object(self, *, Bucket, Key):
        self.calls.append(("delete", Bucket, Key))
        if self.delete_error:
            raise self.delete_error
        self.objects.pop((Bucket, Key), None)

    def head_object(self, *, Bucket, Key):
        self.calls.append(("head", Bucket, Key))
        if self.head_status != 200:
            raise ClientError(
                {"ResponseMetadata": {"HTTPStatusCode": self.head_status}}, "HeadObject"
            )
        return {}


class Session:
    def __init__(self):
        self.posts = []
        self.gets = []
        self.invalid_error = -8
        self.convert_count = 0
        self.result_url = (
            f"http://localhost:29843/cache/files/{MARKER}/output.pdf?signature=contract"
        )
        self.pdf = b"%PDF-1.7\n" + b"contract fixture\n" * 20
        self.callback = response(403, value={"error": 1})
        self.conversion_error = None

    def get(self, url, **_kwargs):
        self.gets.append(url)
        if url.endswith("/ready"):
            return response(value={"status": "pass"})
        if url.endswith("/healthcheck"):
            return response(text="true")
        if "/cache/files/" in url:
            return response(content=self.pdf)
        raise AssertionError("An unapproved endpoint was requested")

    def post(self, url, *, json, **_kwargs):
        self.posts.append((url, json))
        if "/callback/" in url:
            return self.callback
        self.convert_count += 1
        if self.convert_count == 1:
            return response(value={"error": self.invalid_error})
        if self.conversion_error:
            raise self.conversion_error
        claims = jwt.decode(
            json["token"], os.environ["ONLYOFFICE_JWT_SECRET"], algorithms=["HS256"]
        )
        if claims["key"] != MARKER or claims["url"] != json["url"]:
            raise AssertionError("The actual request parameters were not signed")
        return response(value={"endConvert": True, "fileUrl": self.result_url})


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.storage = Storage()
        self.session = Session()
        self.signer = SimpleNamespace(
            generate_presigned_url=lambda *_args, **_kwargs: (
                f"http://localhost:23900/{BUCKET}/{KEY}?signature=contract"
            )
        )
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, ENVIRONMENT, clear=True).start()
        patch.object(verifier.requests, "Session", return_value=self.session).start()
        self.client = patch.object(
            verifier.boto3, "client", side_effect=[self.storage, self.signer]
        ).start()

    def run_probe(self, **kwargs):
        return verifier.verify(
            marker=MARKER,
            expected_bucket=BUCKET,
            expected_origin=ENVIRONMENT["ONLYOFFICE_PUBLIC_URL"],
            expected_storage_origin=ENVIRONMENT["BUCKET_LABORATORY_PUBLIC_ADDRESS"],
            **kwargs,
        )

    def assert_owned_cleanup(self):
        self.assertEqual(
            self.storage.calls[-2:], [("delete", BUCKET, KEY), ("head", BUCKET, KEY)]
        )
        self.assertFalse(self.storage.objects)

    def test_success_requires_authenticated_conversion_callback_refusal_and_owned_cleanup(
        self,
    ):
        result = self.run_probe()
        self.assertEqual(
            result,
            {
                "health": True,
                "conversion": True,
                "jwt": True,
                "callback_refused": True,
                "cleaned": True,
            },
        )
        self.assert_owned_cleanup()
        self.assertEqual(self.storage.calls[0], ("put", BUCKET, KEY))
        self.assertEqual(len(self.session.posts), 3)
        self.assertTrue(
            self.session.gets[-1].startswith(
                ENVIRONMENT["ONLYOFFICE_INTERNAL_URL"] + "/cache/files/"
            )
        )
        self.assertFalse(self.session.trust_env)
        self.assertEqual(self.session.verify, ENVIRONMENT["REQUESTS_CA_BUNDLE"])
        for call in self.client.call_args_list:
            self.assertEqual(call.kwargs["config"].proxies, {})

    def test_running_endpoint_changes_are_rejected_before_network_or_storage(self):
        changes = (
            ("BUCKET_LABORATORY_ADDRESS", "https://foreign.invalid"),
            ("BUCKET_LABORATORY_ACCESS_KEY", ""),
            ("BUCKET_LABORATORY_SECRET_KEY", ""),
            ("BUCKET_LABORATORY_PUBLIC_ADDRESS", "http://localhost:23901"),
            ("ONLYOFFICE_INTERNAL_URL", "https://foreign.invalid"),
            ("ONLYOFFICE_PUBLIC_URL", "http://localhost:29844"),
            ("ONLYOFFICE_CALLBACK_ORIGIN", "https://foreign.invalid"),
            ("REQUESTS_CA_BUNDLE", "foreign-ca.crt"),
        )
        self.storage.objects[BUCKET, "existing-document.docx"] = b"preserved"
        original = dict(self.storage.objects)
        for name, value in changes:
            with self.subTest(setting=name), patch.dict(os.environ, {name: value}):
                with self.assertRaises(RuntimeError):
                    self.run_probe()
                self.client.assert_not_called()
                self.assertEqual(self.storage.calls, [])
                self.assertEqual(self.storage.objects, original)
                self.assertEqual((self.session.posts, self.session.gets), ([], []))

    def test_negative_jwt_probe_always_uses_a_different_key_from_valid_configuration(
        self,
    ):
        secret = "invalid-local-verification-key-0000000000"
        with patch.dict(os.environ, {"ONLYOFFICE_JWT_SECRET": secret}):
            self.assertTrue(self.run_probe()["jwt"])
            with self.assertRaises(jwt.InvalidSignatureError):
                jwt.decode(
                    self.session.posts[0][1]["token"], secret, algorithms=["HS256"]
                )
        self.assert_owned_cleanup()

    def test_owner_expectations_and_safe_origins_are_required(self):
        for origin in (
            None,
            "https://foreign.invalid",
            "http://localhost:23900@foreign.invalid",
            "http://localhost:23900/path",
            "http://user@localhost:23900",
            "http://localhost:99999",
        ):
            with self.subTest(origin=origin), self.assertRaises(RuntimeError):
                verifier.verify(
                    marker=MARKER,
                    expected_bucket=BUCKET,
                    expected_origin=ENVIRONMENT["ONLYOFFICE_PUBLIC_URL"],
                    expected_storage_origin=origin,
                )
        with self.assertRaises(RuntimeError):
            verifier.verify(marker=MARKER)
        self.client.assert_not_called()
        self.assertEqual((self.session.posts, self.session.gets), ([], []))

    def test_cleanup_requires_explicit_marker_and_fixed_local_storage(self):
        for marker in (None, "", False, "../foreign"):
            with self.subTest(marker=marker), self.assertRaises(RuntimeError):
                verifier.verify(marker=marker, cleanup=True, expected_bucket=BUCKET)
        with (
            patch.dict(
                os.environ, {"BUCKET_LABORATORY_ADDRESS": "https://foreign.invalid"}
            ),
            self.assertRaises(RuntimeError),
        ):
            self.run_probe(cleanup=True)
        self.client.assert_not_called()
        self.assertEqual(self.storage.calls, [])

    def test_cleanup_recovers_owned_object_while_editor_configuration_is_broken(self):
        self.storage.objects[BUCKET, KEY] = b"owned interrupted input"
        with patch.dict(
            os.environ,
            {
                "ONLYOFFICE_INTERNAL_URL": "https://foreign.invalid",
                "REQUESTS_CA_BUNDLE": "missing.crt",
            },
        ):
            result = self.run_probe(cleanup=True)
        self.assertTrue(result["cleaned"])
        self.assert_owned_cleanup()
        self.assertEqual(self.client.call_count, 1)
        self.assertEqual((self.session.posts, self.session.gets), ([], []))

    def test_download_error_does_not_prove_jwt_rejection(self):
        self.session.invalid_error = -4
        result = self.run_probe()
        self.assertFalse(
            result["jwt"], "A download failure must not be counted as a refused JWT"
        )
        self.assert_owned_cleanup()

    def test_wrong_result_origin_is_not_downloaded_and_fixture_is_cleaned(self):
        self.session.result_url = (
            "https://foreign.example/cache/files/other/output.pdf?credential=untrusted"
        )
        with self.assertRaisesRegex(RuntimeError, "origin"):
            self.run_probe()
        self.assertFalse(any("foreign.example" in url for url in self.session.gets))
        self.assert_owned_cleanup()

    def test_conversion_transport_failure_still_releases_only_its_owned_object(self):
        self.session.conversion_error = verifier.requests.ConnectionError(
            "synthetic transport failure"
        )
        with self.assertRaises(verifier.requests.ConnectionError):
            self.run_probe()
        self.assert_owned_cleanup()

    def test_missing_pdf_or_wrong_callback_refusal_cannot_pass(self):
        self.session.pdf = b"<html>not a document</html>"
        self.session.callback = response(200, value={"error": 0})
        result = self.run_probe()
        self.assertFalse(result["conversion"])
        self.assertFalse(result["callback_refused"])
        self.assert_owned_cleanup()

    def test_cleanup_recovery_does_not_upload_convert_or_call_the_application(self):
        result = self.run_probe(cleanup=True)
        self.assertTrue(result["cleaned"])
        self.assertEqual(
            self.storage.calls, [("delete", BUCKET, KEY), ("head", BUCKET, KEY)]
        )
        self.assertEqual((self.session.posts, self.session.gets), ([], []))

    def test_invalid_identity_or_foreign_bucket_fails_before_storage_or_network(self):
        for marker, bucket in (("../foreign", BUCKET), (MARKER, "foreign-bucket")):
            with (
                self.subTest(marker=marker, bucket=bucket),
                self.assertRaises(RuntimeError),
            ):
                verifier.verify(marker=marker, expected_bucket=bucket)
        self.client.assert_not_called()
        self.assertEqual(self.storage.calls, [])
        self.assertEqual((self.session.posts, self.session.gets), ([], []))

    def test_cleanup_access_error_is_not_treated_as_missing(self):
        self.storage.head_status = 403
        with self.assertRaises(ClientError):
            self.run_probe(cleanup=True)
        self.assertEqual(
            self.storage.calls, [("delete", BUCKET, KEY), ("head", BUCKET, KEY)]
        )

    def test_object_remaining_after_delete_is_not_reported_clean(self):
        self.storage.head_status = 200
        self.assertFalse(self.run_probe(cleanup=True)["cleaned"])

    def test_disposable_upload_is_a_real_docx_with_owned_marker(self):
        original = self.storage.put_object
        uploaded = []

        def capture(**kwargs):
            uploaded.append(kwargs["Body"])
            return original(**kwargs)

        self.storage.put_object = capture
        self.run_probe()
        with zipfile.ZipFile(io.BytesIO(uploaded[0])) as package:
            self.assertIn("[Content_Types].xml", package.namelist())
            self.assertIn(MARKER.encode(), package.read("word/document.xml"))
        self.assert_owned_cleanup()


if __name__ == "__main__":
    unittest.main()

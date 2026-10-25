import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import jwt
from freezegun import freeze_time
from lxml import html

from odoo import fields
from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from .editing_service import SECRET
from .laboratory_editing_case import LaboratoryEditingCase
from .laboratory_files_case import PASSWORD
from .laboratory_sample_folder_case import LaboratorySampleFolderCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import EXPIRED, PUBLIC_URL_VARIABLE
from odoo.addons.sol_laboratory.constants.laboratory_files import RAW_DATA, RESULT
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_EDITING_SESSION
from odoo.addons.sol_laboratory.services.laboratory_editor_page import CALLBACK_ORIGIN_VARIABLE
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


@tagged("post_install", "-at_install")
class TestLaboratoryEditorPage(HttpCase, LaboratoryEditingCase, LaboratorySampleFolderCase):
    def setUp(self):
        super().setUp()
        self.enterContext(patch.dict(os.environ, {CALLBACK_ORIGIN_VARIABLE: "https://odoo.lab.example"}))
        self.authenticate(self.tester.login, PASSWORD)

    def page(self, file=None, *, status=200, query="", **options):
        file = self.file if file is None else file
        response = self.url_open(
            f"/medilab/laboratory-files/{file.id or 0}/edit{query}", allow_redirects=False, **options
        )
        self.assertEqual(response.status_code, status, response.text[:200])
        self.assertIn("text/html", response.headers["Content-Type"])
        self.assertEqual(response.headers["Cache-Control"], "private, no-store, max-age=0")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("unsafe-inline", response.headers["Content-Security-Policy"])
        return response

    def config(self, response):
        return json.loads(
            html.fromstring(response.content).get_element_by_id("laboratory-editor").get("data-editor-config")
        )

    def test_open_and_join_preserve_identity_and_signed_configuration(self):
        first = self.config(self.page())
        self.authenticate(self.member.login, PASSWORD)
        second = self.config(self.page())
        session = self.file.editing_session_ids
        self.assertEqual(len(session), 1)
        self.assertEqual(first["document"]["key"], second["document"]["key"])
        self.assertEqual(session.base_version_id, self.first)
        self.assertEqual(first["editorConfig"]["callbackUrl"], second["editorConfig"]["callbackUrl"])
        self.assertTrue(
            first["editorConfig"]["callbackUrl"].startswith(
                "https://odoo.lab.example/medilab/laboratory-files/callback/"
            )
        )
        self.assertEqual(second["editorConfig"]["user"]["id"], str(self.member.id))
        self.assertFalse(second["editorConfig"]["customization"]["forcesave"])
        claims = jwt.decode(second["token"], SECRET, algorithms=["HS256"])
        self.assertEqual(claims["document"]["key"], session.document_key)

    def test_nonmember_missing_and_hidden_sample_do_not_disclose_metadata(self):
        self.authenticate(self.outsider.login, PASSWORD)
        absent = self.env[self.file._name].browse(2147483647)
        hidden = self.page(status=404)
        missing = self.page(absent, status=404)
        self.assertEqual(hidden.content, missing.content)
        self.assertNotIn(self.file.path, hidden.text)
        self.assertFalse(self.file.editing_session_ids)

    def test_sample_visibility_is_checked_by_the_model(self):
        folder = self.folder_of_category(RESULT, name="Private sample")
        file = self.file_of("Secret.xlsx", folder)
        self.save(file, "secret")
        self.tester.group_ids = [Command.unlink(self.env.ref("sol_laboratory.group_permission_sample_read_all").id)]
        self.page(file, status=404)
        self.assertFalse(file.editing_session_ids)

    def test_missing_permission_returns_generic_403(self):
        self.authenticate(self.colleague.login, PASSWORD)
        response = self.page(status=403)
        absent = self.env[self.file._name].browse(2147483647)
        self.assertEqual(response.content, self.page(absent, status=403).content)
        self.assertNotIn(self.file.path, response.text)
        self.assertFalse(self.file.editing_session_ids)

    def test_revoked_membership_is_checked_on_reentry(self):
        self.page()
        self.authenticate(self.member.login, PASSWORD)
        self.folder.member_ids.filtered(lambda row: row.user_id == self.member).unlink()
        self.page(status=404)
        self.assertEqual(len(self.file.editing_session_ids), 1)

    def test_raw_data_non_office_and_empty_files_return_409_without_sessions(self):
        raw = self.file_of("Raw.xlsx", self.folder_of_category(RAW_DATA, name="Instrument"))
        text = self.file_of("Notes.txt")
        empty = self.file_of("Empty.xlsx")
        for file in (raw, text):
            self.save(file, "content")
        for file in (raw, text, empty):
            with self.subTest(file=file.id):
                self.page(file, status=409)
                self.assertFalse(file.editing_session_ids)

    def test_disabled_and_archived_folder_return_409(self):
        self.folder.with_user(self.administrator).action_turn_off()
        self.page(status=409)
        self.folder.with_user(self.administrator).action_archive_folder()
        self.page(status=409)
        self.assertFalse(self.file.editing_session_ids)

    def test_service_down_returns_503_without_a_session(self):
        self.health_check.return_value = False
        self.page(status=503)
        self.assertFalse(self.file.editing_session_ids)

    def test_invalid_origins_fail_closed_before_health_check_or_session_creation(self):
        for variable, value in (
            (PUBLIC_URL_VARIABLE, "https://docs.lab.example/evil?x=1"),
            (CALLBACK_ORIGIN_VARIABLE, "//evil.example"),
        ):
            with self.subTest(variable=variable), patch.dict(os.environ, {variable: value}):
                self.health_check.reset_mock()
                self.page(status=503)
                self.health_check.assert_not_called()
                self.assertFalse(self.file.editing_session_ids)

    def test_config_failure_rolls_back_new_session_and_join_audit(self):
        sessions = type(self.env[MODEL_LABORATORY_EDITING_SESSION])
        with patch.object(
            sessions, "_editor_config", side_effect=LaboratoryFileError("editing_unavailable", "Unavailable")
        ):
            self.page(status=503)
        self.assertFalse(self.file.editing_session_ids)

    def test_login_redirect_ignores_untrusted_targets_and_device_keys(self):
        _device, key = self.sign_in(self.tester, "editor-browser-separation")
        self.assertEqual(self.device_of(key).user_id, self.tester)
        self.authenticate(None, None)
        for target in ("https://evil.example", "//evil.example", "%2f%2fevil.example", "%5cevil.example"):
            response = self.page(status=303, query=f"?redirect={target}", headers={"Authorization": f"Bearer {key}"})
            location = urlsplit(response.headers["Location"])
            self.assertEqual((location.scheme, location.netloc, location.path), ("", "", "/web/login"))
            self.assertEqual(parse_qs(location.query), {"redirect": [f"/medilab/laboratory-files/{self.file.id}/edit"]})

    def test_host_and_query_cannot_change_callback_or_script_origins(self):
        response = self.page(
            query="?callbackUrl=https://evil.example&redirect=//evil.example",
            headers={
                "X-Forwarded-Host": "attacker.example",
            },
        )
        config = self.config(response)
        self.assertTrue(config["editorConfig"]["callbackUrl"].startswith("https://odoo.lab.example/"))
        self.assertNotIn("attacker.example", response.text)
        csp = response.headers["Content-Security-Policy"]
        self.assertIn("script-src 'self' https://docs.lab.example;", csp)
        self.assertNotIn("unsafe-eval", csp)

    def test_user_names_are_json_data_and_never_script_markup(self):
        attack = '</script><img src=x onerror="window.editorXss=1">\u2028\u2029&'
        self.tester.name = attack
        response = self.page()
        self.assertEqual(self.config(response)["editorConfig"]["user"]["name"], attack)
        tree = html.fromstring(response.content)
        self.assertFalse(tree.xpath("//img | //script[not(@src)] | //*[@onerror]"))
        self.assertNotIn("<img src=x", response.text)

    def test_file_titles_are_escaped_as_html_and_json_data(self):
        title = 'Results <img src=x onerror=window.editorXss=1> & "\u2028.xlsx'
        file = self.file_of(title)
        self.save(file, "results")
        response = self.page(file)
        tree = html.fromstring(response.content)
        heading = tree.find(".//h1")
        if heading is None:
            self.fail("The editor did not display a heading.")
        self.assertEqual(heading.text, title)
        self.assertEqual(self.config(response)["document"]["title"], title)
        self.assertFalse(tree.xpath("//img | //script[not(@src)] | //*[@onerror]"))

    def test_translated_model_refusals_are_escaped_as_text(self):
        attack = '<img src=x onerror="window.editorXss=1"> & </script>\u2028'
        sessions = type(self.env[MODEL_LABORATORY_EDITING_SESSION])
        with patch.object(sessions, "_open_for", side_effect=LaboratoryFileError("not_editable", attack)):
            response = self.page(status=409)
        tree = html.fromstring(response.content)
        self.assertEqual(tree.get_element_by_id("editor-status").text_content().strip(), attack.strip())
        self.assertFalse(tree.xpath("//img | //*[@onerror] | //script"))
        self.assertFalse(self.file.editing_session_ids)

    def test_url_lifetime_reentry_keeps_key_and_base_after_competing_upload(self):
        with freeze_time(datetime.now() - timedelta(minutes=20)):
            first = self.config(self.page())
        session = self.file.editing_session_ids
        self.save(self.file, "competing upload", user=self.member)
        session.sudo().last_activity_at = fields.Datetime.now() - timedelta(minutes=20)
        second = self.config(self.page())
        with self.assertRaises(jwt.ExpiredSignatureError):
            jwt.decode(first["token"], SECRET, algorithms=["HS256"])
        jwt.decode(second["token"], SECRET, algorithms=["HS256"])
        self.assertNotEqual(first["document"]["url"], second["document"]["url"])
        self.assertEqual(first["document"]["key"], second["document"]["key"])
        self.assertEqual(session.base_version_id, self.first)
        self.assertEqual(len(self.file.editing_session_ids), 1)

    def test_methods_and_out_of_range_ids_use_html_refusals(self):
        for method in ("POST", "OPTIONS"):
            response = self.page(status=405, method=method)
            self.assertEqual(response.headers["Allow"], "GET, HEAD")
        for value in (0, 2**63):
            self.page(self.env[self.file._name].browse(value), status=404)
        self.assertFalse(self.file.editing_session_ids)

    def test_idle_session_gets_a_new_key_on_explicit_reentry(self):
        first = self.config(self.page())
        session = self.file.editing_session_ids
        session.sudo().last_activity_at = fields.Datetime.now() - timedelta(hours=13)
        second = self.config(self.page())
        self.assertNotEqual(first["document"]["key"], second["document"]["key"])
        self.assertEqual(session.status, EXPIRED)

    def test_english_and_vietnamese_error_pages(self):
        self.health_check.return_value = False
        for language, message in (
            ("en_US", "Online editing is unavailable right now."),
            ("vi_VN", "Hiện không thể chỉnh sửa trực tuyến."),
        ):
            self.tester.lang = language
            self.authenticate(self.tester.login, PASSWORD)
            self.assertIn(message, self.page(status=503).text)
            self.health_check.return_value = True
            ready_page = self.page()
            connecting = "Đang kết nối đến trình chỉnh sửa..." if language == "vi_VN" else "Connecting to the editor..."
            self.assertTrue(connecting in ready_page.text, "The editor connecting message was not translated.")
            self.health_check.return_value = False

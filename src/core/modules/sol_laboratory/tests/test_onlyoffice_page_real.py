"""Opt-in released page, browser login, native keyboard editing and immutable Garage save."""

import hashlib
import io
import json
import os
import socket
import time
import uuid
import zipfile
from pathlib import Path
from unittest import SkipTest

import requests

from odoo.tests import new_test_user, tagged

from . import test_onlyoffice_real
from .editing_service import SECRET
from .laboratory_editing_http_case import LaboratoryEditingHttpCase
from odoo.addons.sol_laboratory.constants.laboratory_bucket import PUBLIC_ADDRESS_VARIABLE
from odoo.addons.sol_laboratory.constants.laboratory_files import FILE_WRITE, MEMBER_ROLE
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services import laboratory_bucket
from odoo.addons.sol_laboratory.services.laboratory_editor_page import CALLBACK_ORIGIN_VARIABLE


@tagged("post_install", "-at_install", "-standard", "onlyoffice_page_real")
class TestOnlyofficePageReal(LaboratoryEditingHttpCase):
    HTTP_INTERFACE = "0.0.0.0"
    HTTP_LIMIT_TIME_REAL = 1200

    @classmethod
    def setUpClass(cls):
        if os.environ.get("ONLYOFFICE_PAGE_REAL") != "1":
            raise SkipTest("Requires the owned page browser and loopback storage proxy.")
        super().setUpClass()

    @classmethod
    def editing_internal_url(cls):
        return "http://documentserver"

    @classmethod
    def editing_public_url(cls):
        return "http://localhost:8081"

    @classmethod
    def server_environment(cls):
        port = cls.http_url.rsplit(":", 1)[1]
        return {
            CALLBACK_ORIGIN_VARIABLE: f"http://{socket.gethostname()}:{port}",
            PUBLIC_ADDRESS_VARIABLE: "http://localhost:3900",
        }

    def setUp(self):
        self.marker = "MEDILAB_PAGE_" + uuid.uuid4().hex
        self.extension = next(extension for extension in ("docx", "xlsx", "pptx") if extension in self._testMethodName)
        super().setUp()
        self.addCleanup(self.save_diagnostics)

    def save_diagnostics(self):
        directory = Path(os.environ["ONLYOFFICE_EVIDENCE_DIR"])
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        lines = [
            line.split("ONLYOFFICE callback ", 1)[1]
            for line in self.server_messages().splitlines()
            if "ONLYOFFICE callback status=" in line
        ]
        (directory / "page-callback-outcomes.json").write_text(json.dumps(lines, indent=2) + "\n")

    def prepare(self, env):
        fixture = test_onlyoffice_real.TestOnlyofficeReal.prepare(self, env)
        env.ref("base.user_admin").name = '</script><img src=x onerror="window.editorXss=1">&\u2028\u2029'
        if "two_person" in self._testMethodName:
            member = new_test_user(
                env, login=self.marker, password="page-only", groups="base.group_user," + LABORATORY_FILES_GROUP
            )
            env["medilab.laboratory.folder.member"].create(
                {"folder_id": fixture[0], "user_id": member.id, "role": MEMBER_ROLE}
            )
            env["medilab.laboratory.file"].browse(fixture[1]).with_user(member)._check_file_access(FILE_WRITE)
        return fixture

    def prepare_session(self, env):
        return 0, "", "", env.ref("base.user_admin").id

    def test_docx_login_page_keyboard_save(self):
        self.assert_page_save()

    def test_docx_two_person_save(self):
        self.assert_page_save()

    def test_xlsx_two_person_save(self):
        self.assert_page_save()

    def test_pptx_two_person_save(self):
        self.assert_page_save()

    def assert_page_save(self):
        self.assertFalse(self.committed(lambda env: bool(self.session(env))))
        port = self.http_url.rsplit(":", 1)[1]
        hold = int(os.environ.get("ONLYOFFICE_PAGE_HOLD_SECONDS", "3"))
        self.assertIn(hold, (3, 920))
        result = requests.post(
            "http://page-browser:3000/page",
            json={
                "url": f"http://runner:{port}/medilab/laboratory-files/{self.file_id}/edit",
                "marker": self.marker,
                "extension": self.extension,
                "coeditor": {"login": self.marker, "password": "page-only"}
                if "two_person" in self._testMethodName
                else None,
                "holdSeconds": hold,
            },
            timeout=hold + 180,
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()["xssAbsent"])
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.committed(lambda env: self.session(env).status) == "committed":
                break
            time.sleep(0.5)

        def read(env):
            session = self.session(env)
            version = session.committed_version_id
            return (
                session.status,
                version.sha256,
                version.content_id.object_key,
                version.user_id.id,
                len(session.file_id.version_ids),
                session._callback_token(),
            )

        status, digest, key, user, count, capability = self.committed(read)
        self.assertEqual(status, "committed")
        self.assertEqual(count, 2)
        self.assertEqual(user, self.editor_id)
        with laboratory_bucket.read(key) as chunks:
            self.content = b"".join(chunks)
        self.saved_sha = hashlib.sha256(self.content).hexdigest()
        self.assertEqual(self.saved_sha, digest)
        with zipfile.ZipFile(io.BytesIO(self.content)) as archive:
            xml = b"\n".join(archive.read(name) for name in archive.namelist() if name.endswith(".xml"))
            self.assertTrue(self.marker.encode() in xml, "The primary editor marker was not saved.")
            if "two_person" in self._testMethodName:
                self.assertTrue((self.marker + "_MEMBER").encode() in xml, "The second editor marker was not saved.")
        self.assertNotIn(capability, self.server_messages())
        self.assertNotIn(SECRET, self.server_messages())
        directory = Path(os.environ["ONLYOFFICE_EVIDENCE_DIR"])
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.environ.get("ONLYOFFICE_DESKTOP_PROBE") == "1":
            (directory / "desktop-ready.json").write_text(
                json.dumps(
                    {
                        "url": f"http://{socket.gethostname()}:{port}",
                        "folder": self.folder_id,
                        "file": self.file_id,
                        "sha256": digest,
                    }
                )
                + "\n"
            )
            deadline = time.monotonic() + 180
            result_path = directory / "desktop-result.json"
            while not result_path.exists() and time.monotonic() < deadline:
                time.sleep(0.5)
            self.assertTrue(result_path.exists(), "The desktop client observer did not complete in its budget.")
            self.assertEqual(json.loads(result_path.read_text())["status"], "PASS")
        name = self.extension + ("-two-person" if "two_person" in self._testMethodName else "")
        (directory / f"page-{name}.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "browser": result.json(),
                    "version_count": count,
                    "sha256": digest,
                    "size": len(self.content),
                    "marker_present": True,
                    "transport": "isolated HTTP with loopback proxies; no ingress/TLS claim",
                },
                indent=2,
            )
            + "\n"
        )

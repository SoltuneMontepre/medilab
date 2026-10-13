from xmlrpc.client import Fault

from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from .audit_case import AuditLookup
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_CHEMICAL, MODEL_MOBILE_DEVICE

PASSWORD = "Lab-Password-2026"


@tagged("post_install", "-at_install")
class TestAuditSessions(AuditLookup, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor = new_test_user(
            cls.env,
            login="editor",
            password=PASSWORD,
            groups="base.group_user,sol_laboratory.group_permission_chemical_edit_all",
        )
        cls.administrator = new_test_user(
            cls.env, login="administrator", password=PASSWORD, groups="sol_laboratory.group_role_administrator"
        )
        cls.chemical = cls.env[MODEL_CHEMICAL].create({"code": "HC-103", "name": "Methanol"})

    def test_signing_in_and_out_writes_entries(self):
        self.authenticate(None, None)
        self.url_open("/web/login", data={"login": "editor", "password": PASSWORD, "csrf_token": self.csrf_token()})
        self.assertEqual(self.entries(self.editor, "login").source, "screen")

        self.authenticate("editor", PASSWORD)
        self.url_open("/web/session/logout", data={"csrf_token": self.csrf_token()})
        self.authenticate("editor", PASSWORD)
        self.make_jsonrpc_request("/web/session/destroy")

        logouts = self.entries(self.editor, "logout")
        self.assertEqual(len(logouts), 2)
        self.assertEqual(logouts.user_id, self.editor)

    @mute_logger("odoo.addons.rpc.controllers.xmlrpc")
    def test_the_external_api_is_its_own_source(self):
        db = self.env.cr.dbname
        uid = self.xmlrpc_common.authenticate(db, "editor", PASSWORD, {})

        self.xmlrpc_object.execute_kw(
            db, uid, PASSWORD, MODEL_CHEMICAL, "write", [[self.chemical.id], {"grade": "HPLC"}]
        )

        self.assertEqual(self.entries(self.editor, "login").source, "api")
        edit = self.entries(self.chemical, "edit")
        self.assertEqual((edit.source, edit.user_id), ("api", self.editor))

    def test_the_mobile_app_is_the_api(self):
        self.authenticate("editor", PASSWORD)

        result = self.make_jsonrpc_request("/medilab/mobile/register", {"token": "fcm-token", "platform": "android"})

        entry = self.entries(self.env[MODEL_MOBILE_DEVICE].browse(result["id"]), "create")
        self.assertEqual((entry.source, entry.user_id), ("api", self.editor))

    @mute_logger("odoo.http", "odoo.addons.rpc.controllers.xmlrpc")
    def test_an_administrator_cannot_remove_an_entry_through_the_api(self):
        db = self.env.cr.dbname
        uid = self.xmlrpc_common.authenticate(db, "administrator", PASSWORD, {})
        entry = self.entries(self.chemical, "create")

        with self.assertRaises(Fault):
            self.xmlrpc_object.execute_kw(db, uid, PASSWORD, MODEL_AUDIT_ENTRY, "unlink", [entry.ids])

        self.assertTrue(entry.exists())

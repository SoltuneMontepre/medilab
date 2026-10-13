from xmlrpc.client import Fault

from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_CHEMICAL

PASSWORD = "Lab-Password-2026"


@tagged("post_install", "-at_install")
class TestAuditSessions(HttpCase):
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

    def entries(self, document_model, document_id, action):
        return (
            self.env[MODEL_AUDIT_ENTRY]
            .sudo()
            .search(
                [("document_model", "=", document_model), ("document_id", "=", document_id), ("action", "=", action)]
            )
        )

    def test_signing_in_and_out_writes_entries(self):
        self.authenticate(None, None)
        self.url_open("/web/login", data={"login": "editor", "password": PASSWORD, "csrf_token": self.csrf_token()})
        self.assertEqual(self.entries("res.users", self.editor.id, "login").source, "screen")

        self.authenticate("editor", PASSWORD)
        self.url_open("/web/session/logout", data={"csrf_token": self.csrf_token()})
        self.authenticate("editor", PASSWORD)
        self.make_jsonrpc_request("/web/session/destroy")

        logouts = self.entries("res.users", self.editor.id, "logout")
        self.assertEqual(len(logouts), 2)
        self.assertEqual(logouts.user_id, self.editor)

    @mute_logger("odoo.addons.rpc.controllers.xmlrpc")
    def test_the_external_api_is_its_own_source(self):
        db = self.env.cr.dbname
        uid = self.xmlrpc_common.authenticate(db, "editor", PASSWORD, {})

        self.xmlrpc_object.execute_kw(
            db, uid, PASSWORD, MODEL_CHEMICAL, "write", [[self.chemical.id], {"grade": "HPLC"}]
        )

        self.assertEqual(self.entries("res.users", self.editor.id, "login").source, "api")
        edit = self.entries(MODEL_CHEMICAL, self.chemical.id, "edit")
        self.assertEqual((edit.source, edit.user_id), ("api", self.editor))

    @mute_logger("odoo.http", "odoo.addons.rpc.controllers.xmlrpc")
    def test_an_administrator_cannot_remove_an_entry_through_the_api(self):
        db = self.env.cr.dbname
        uid = self.xmlrpc_common.authenticate(db, "administrator", PASSWORD, {})
        entry = self.entries(MODEL_CHEMICAL, self.chemical.id, "create")

        with self.assertRaises(Fault):
            self.xmlrpc_object.execute_kw(db, uid, PASSWORD, MODEL_AUDIT_ENTRY, "unlink", [entry.ids])

        self.assertTrue(entry.exists())

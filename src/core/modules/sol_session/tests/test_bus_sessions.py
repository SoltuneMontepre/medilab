import importlib

from odoo import sql_db
from odoo.tests import HttpCase, tagged

from odoo.addons.sol_session.session_store import TABLE

bus_dispatcher = importlib.import_module("odoo.addons.bus.bus_dispatcher")
http_session = importlib.import_module("odoo.http.session")


@tagged("post_install", "-at_install")
class TestBusSessions(HttpCase):
    """The bus keeps a websocket open while its session row is valid, as it does for a session file."""

    def setUp(self):
        super().setUp()
        self.store = http_session.session_store()
        self.authenticate("admin", "admin")
        self.sids = [self.session.sid]
        self.addCleanup(self._remove_sessions)

    def _remove_sessions(self):
        with sql_db.db_connect(self.env.cr.dbname).cursor() as cursor:
            cursor.execute(f"DELETE FROM {TABLE} WHERE sid = ANY(%s)", [self.sids])

    def _check(self, *sessions):
        return bus_dispatcher.check_sessions(self.env.cr, sessions)

    def test_signed_in_session_keeps_its_websocket(self):
        resolved = self._check(self.session)

        self.assertEqual(resolved[self.session.sid].uid, self.env.ref("base.user_admin").id)

    def test_signed_out_session_loses_its_websocket(self):
        self.store.delete(self.session)

        self.assertEqual(self._check(self.session), {})

    def test_session_without_user_keeps_its_websocket(self):
        visitor = self.store.new()

        self.assertIs(self._check(visitor)[visitor.sid], visitor)

    def test_rotated_session_resolves_to_its_successor(self):
        successor = self.store.new()
        successor.update(dict(self.session))
        successor["session_token"] = (
            self.env["res.users"].browse(self.session.uid)._compute_session_token(successor.sid)
        )
        self.store.save(successor)
        self.sids.append(successor.sid)
        rotated = self.store.get(self.session.sid)
        rotated["next_sid"] = successor.sid
        self.store.save(rotated)

        self.assertEqual(self._check(self.session)[self.session.sid].sid, successor.sid)

    def test_session_with_a_wrong_token_loses_its_websocket(self):
        stored = self.store.get(self.session.sid)
        stored["session_token"] = "0" * 64
        self.store.save(stored)

        self.assertEqual(self._check(self.session), {})

import importlib
import secrets

from odoo import sql_db
from odoo.tests import HttpCase, tagged

from odoo.addons.sol_session.session_store import TABLE, DatabaseSessionStore

http_session = importlib.import_module("odoo.http.session")


@tagged("post_install", "-at_install")
class TestDatabaseSessionStore(HttpCase):
    """Each store stands for another Odoo process: a session one saves, another reads."""

    def setUp(self):
        super().setUp()
        self.store = DatabaseSessionStore(database=self.env.cr.dbname)
        self.other = DatabaseSessionStore(database=self.env.cr.dbname)
        self.sids = []
        self.addCleanup(self._remove_sessions)

    def _remove_sessions(self):
        with sql_db.db_connect(self.env.cr.dbname).cursor() as cursor:
            cursor.execute(f"DELETE FROM {TABLE} WHERE sid = ANY(%s)", [self.sids])

    def _saved(self, **data):
        session = self.store.new()
        session.update(data)
        self.store.save(session)
        self.sids.append(session.sid)
        return session

    def test_store_is_used_for_requests(self):
        self.assertIsInstance(http_session.session_store(), DatabaseSessionStore)

    def test_session_saved_by_one_process_is_read_by_another(self):
        session = self._saved(context={"lang": "vi_VN"})

        read = self.other.get(session.sid)

        self.assertFalse(read.is_new)
        self.assertEqual(read["context"], {"lang": "vi_VN"})

    def test_saving_again_replaces_the_data(self):
        session = self._saved(debug="")
        session["debug"] = "1"
        self.store.save(session)

        self.assertEqual(self.other.get(session.sid)["debug"], "1")

    def test_unknown_session_is_new_unless_its_id_is_kept(self):
        sid = self.store.generate_key()

        self.assertNotEqual(self.store.get(sid).sid, sid)
        kept = self.store.get(sid, keep_sid=True)
        self.assertEqual(kept.sid, sid)
        self.assertFalse(dict(kept))

    def test_invalid_id_gives_a_new_session(self):
        self.assertTrue(self.store.get("not a session id").is_new)

    def test_deleted_session_is_gone_for_every_process(self):
        session = self._saved(uid=1)

        self.store.delete(session)

        self.assertTrue(self.other.get(session.sid).is_new)

    def test_identifiers_find_and_delete_sessions_by_their_stored_bytes(self):
        session = self._saved(uid=1)
        identifier = session.sid[: http_session.STORED_SESSION_BYTES]
        missing = secrets.token_urlsafe(64)[: http_session.STORED_SESSION_BYTES]

        self.assertEqual(self.other.get_missing_session_identifiers([identifier, missing]), {missing})

        self.other.delete_from_identifiers([identifier, "%"])

        self.assertEqual(self.store.get_missing_session_identifiers([identifier]), {identifier})

    def test_vacuum_removes_only_sessions_older_than_the_lifetime(self):
        old = self._saved(uid=1)
        recent = self._saved(uid=2)
        with sql_db.db_connect(self.env.cr.dbname).cursor() as cursor:
            cursor.execute(f"UPDATE {TABLE} SET write_date = write_date - interval '2 hours' WHERE sid = %s", [old.sid])

        self.store.vacuum(max_lifetime=3600)

        self.assertTrue(self.other.get(old.sid).is_new)
        self.assertEqual(self.other.get(recent.sid)["uid"], 2)

    def test_signed_in_session_is_served_by_another_process(self):
        self.authenticate("admin", "admin")
        self.sids.append(self.session.sid)

        response = self.url_open("/odoo")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("/web/login", response.url)
        self.assertEqual(self.other.get(self.session.sid).uid, self.env.ref("base.user_admin").id)

"""Sign-in sessions kept in a table of the configured database instead of files on the pod's disk, so every Odoo
process, and both colours of a blue-green release, read and write the same sessions."""

import importlib
import json
import logging

from odoo import sql_db
from odoo.tools import config

http_session = importlib.import_module("odoo.http.session")

_logger = logging.getLogger(__name__)

TABLE = "sol_http_session"
# Serializes creating the table, which every worker tries on its first use.
CREATE_LOCK = 0x501_5E55
IDENTIFIER_LENGTH = http_session.STORED_SESSION_BYTES


def database_name():
    names = config["db_name"]
    if isinstance(names, str):
        names = [name for name in names.split(",") if name]
    return names[0] if len(names) == 1 else None


class DatabaseSessionStore(http_session.SessionStore):
    """Odoo's session store with each session as a row of `sol_http_session`, its data as JSON."""

    def __init__(self, /, path=None, session_cls=http_session.Session, database=None):
        super().__init__(path=path, session_cls=session_cls)
        self.database = database or database_name()
        self.table_ready = False

    def _cursor(self):
        cursor = sql_db.db_connect(self.database).cursor()
        if not self.table_ready:
            try:
                self._create_table(cursor)
            except Exception:
                cursor.close()
                raise
            self.table_ready = True
        return cursor

    def _create_table(self, cursor):
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [CREATE_LOCK])
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                sid varchar(86) PRIMARY KEY,
                data jsonb NOT NULL,
                write_date timestamp NOT NULL
            );
            CREATE INDEX IF NOT EXISTS {TABLE}_identifier_index ON {TABLE} (left(sid, {IDENTIFIER_LENGTH}));
            CREATE INDEX IF NOT EXISTS {TABLE}_write_date_index ON {TABLE} (write_date);
            """
        )
        cursor.commit()

    def save(self, session):
        if not self.is_valid_session_id(session.sid):
            raise ValueError(f"Invalid session id {session.sid!r}")
        with self._cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {TABLE} (sid, data, write_date) VALUES (%s, %s, now() AT TIME ZONE 'UTC')
                ON CONFLICT (sid) DO UPDATE SET data = EXCLUDED.data, write_date = EXCLUDED.write_date
                """,
                [session.sid, json.dumps(dict(session))],
            )

    def delete(self, session):
        with self._cursor() as cursor:
            cursor.execute(f"DELETE FROM {TABLE} WHERE sid = %s", [session.sid])

    def get(self, sid, *, keep_sid=False):
        if not self.is_valid_session_id(sid):
            return self.new()
        with self._cursor() as cursor:
            cursor.execute(f"SELECT data FROM {TABLE} WHERE sid = %s", [sid])
            row = cursor.fetchone()
        if row:
            return self.session_cls(row[0], sid, new=False)
        if keep_sid:
            return self.session_cls({}, sid, new=False)
        return self.new()

    def vacuum(self, max_lifetime=http_session.SESSION_LIFETIME):
        with self._cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {TABLE} WHERE write_date < now() AT TIME ZONE 'UTC' - make_interval(secs => %s)",
                [max_lifetime],
            )

    def get_missing_session_identifiers(self, identifiers):
        identifiers = set(identifiers)
        if not identifiers:
            return identifiers
        with self._cursor() as cursor:
            cursor.execute(
                f"SELECT DISTINCT left(sid, {IDENTIFIER_LENGTH}) FROM {TABLE} "
                f"WHERE left(sid, {IDENTIFIER_LENGTH}) = ANY(%s)",
                [list(identifiers)],
            )
            found = {row[0] for row in cursor.fetchall()}
        return identifiers - found

    def delete_from_identifiers(self, identifiers):
        valid = [identifier for identifier in identifiers if http_session._session_identifier_re.match(identifier)]
        if not valid:
            return
        with self._cursor() as cursor:
            cursor.execute(f"DELETE FROM {TABLE} WHERE left(sid, {IDENTIFIER_LENGTH}) = ANY(%s)", [valid])


def use_database_sessions():
    """Post-load hook: from now on `session_store()` returns the database store. Needs exactly one database, as
    production's `db_name`; otherwise the sessions stay in files."""
    if not database_name():
        _logger.warning("Sessions stay in files: db_name does not name exactly one database.")
        return
    if issubclass(http_session.SessionStore, DatabaseSessionStore):
        return
    http_session.SessionStore = DatabaseSessionStore
    http_session.session_store.cache_clear()
    _logger.info("Sessions are kept in the %s table of %s.", TABLE, database_name())

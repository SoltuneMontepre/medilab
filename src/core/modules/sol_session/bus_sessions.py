"""The bus closes every websocket whose session it cannot find. It looks for session files, so with the sessions in the
database it is given this check, which reads their rows instead."""

import hashlib
import hmac
import importlib
import time

from odoo.sql_db import SQL
from odoo.tools.misc import consteq

http_session = importlib.import_module("odoo.http.session")


def check_sessions(cr, sessions):
    """`odoo.addons.bus.session_helpers.check_sessions` reading the sessions' rows in one query: returns the valid
    sessions, keyed by the given sid, which differs from the session's own sid once it was rotated."""
    store = http_session.session_store()
    now = time.time()
    resolved = {}
    signed_in = []
    for session in sessions:
        if session.sid in resolved or session.sid in signed_in:
            continue
        if session.uid is None:
            resolved[session.sid] = session
        else:
            signed_in.append(session.sid)
    to_check = _current_sessions(store, signed_in, now)
    if to_check:
        resolved.update(_with_valid_tokens(cr, to_check))
    return resolved


def _current_sessions(store, sids, now):
    """The stored session of each sid, or its successor once rotated, unless it is gone or past its deletion time."""
    stored = store.get_many(sids)
    successors = store.get_many([session["next_sid"] for session in stored.values() if "next_sid" in session])
    current = {}
    for sid in sids:
        session = stored.get(sid)
        if session is not None and "next_sid" in session:
            session = successors.get(session["next_sid"])
        if session is None:
            continue
        store.delete_old_sessions(session)
        if "deletion_time" in session and session["deletion_time"] <= now:
            continue
        current[sid] = session
    return current


def _with_valid_tokens(cr, sessions_by_sid):
    """The sessions whose token still matches their user's, computed as `res.users._compute_session_token` does."""
    helpers = importlib.import_module("odoo.addons.bus.session_helpers")
    uids = {session.uid for session in sessions_by_sid.values()}
    query_params = helpers._get_session_token_query_params(cr, uids)
    cr.execute(SQL("SELECT %(select)s FROM %(from)s %(joins)s WHERE %(where)s GROUP BY %(group_by)s", **query_params))
    id_index = next(index for index, column in enumerate(cr.description) if column.name == "id")
    keys_by_uid = {}
    for row in cr.fetchall():
        values = tuple((column.name, row[index]) for index, column in enumerate(cr.description))
        keys_by_uid[row[id_index]] = str(tuple((name, value) for name, value in values if value is not None)).encode()
    valid = {}
    for sid, session in sessions_by_sid.items():
        key = keys_by_uid.get(session.uid)
        if not key:
            continue
        token = hmac.new(key, session.sid.encode(), hashlib.sha256).hexdigest()
        if consteq(token, session.session_token):
            valid[sid] = session
    return valid


def use_database_session_checks():
    """Gives the bus this check, where it imported its own."""
    try:
        helpers = importlib.import_module("odoo.addons.bus.session_helpers")
        dispatcher = importlib.import_module("odoo.addons.bus.bus_dispatcher")
    except ImportError:
        return
    setattr(helpers, "check_sessions", check_sessions)
    setattr(dispatcher, "check_sessions", check_sessions)

import threading
import time

from odoo import api, sql_db
from odoo.api import SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.http.retrying import retrying
from odoo.orm.environments import Transaction
from odoo.tests import TransactionCase
from odoo.tools import mute_logger

# How long the first action keeps its transaction open once the second one is acting, so the second waits on it.
HOLD_SECONDS = 0.5


class LaboratoryFilesConcurrencyCase(TransactionCase):
    """Two real database transactions acting on laboratory files at once, the second one through Odoo's request
    retrying. What the tests commit is theirs to remove."""

    def committed(self, work):
        with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
            return work(self.environment(cursor))

    def environment(self, cursor):
        # An environment looks its registry up by name, which waits on the lock the test run holds, so the thread of
        # these tests would never get one; they use the registry already loaded.
        cursor.transaction = Transaction(self.registry)
        cursor.transaction._check_signaling(cursor)
        return api.Environment(cursor, SUPERUSER_ID, {})

    def race(self, first_action, second_action):
        """The first action does its work and keeps its transaction open until the second one is acting, then commits.
        The second action runs as a request does, through Odoo's retrying. The number of times the second one ran, and
        the id of the record it returned or the refusal it was refused with."""
        stored = threading.Event()
        second_acting = threading.Event()
        errors = []

        def first():
            try:
                with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
                    env = self.environment(cursor)
                    first_action(env)
                    env.flush_all()
                    # Committing resets the transaction, which also looks the registry up by name; the work is flushed,
                    # so the cursor commits it without one.
                    cursor.transaction = None
                    stored.set()
                    if not second_acting.wait(timeout=10):
                        errors.append(TimeoutError("the second action never started"))
                        return
                    time.sleep(HOLD_SECONDS)
            except Exception as error:
                errors.append(error)
            finally:
                stored.set()

        attempts = []
        thread = threading.Thread(target=first)
        thread.start()
        try:
            with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
                env = self.environment(cursor)

                def run():
                    attempts.append(len(attempts) + 1)
                    if len(attempts) == 1:
                        self.assertTrue(stored.wait(timeout=10), "the first action never did its work")
                        second_acting.set()
                    return second_action(env).id

                with mute_logger("odoo.sql_db", "odoo.http.retrying"):
                    try:
                        result = retrying(run, env)
                    except UserError as refusal:
                        # The cursor would commit what the refused action did before it was refused.
                        cursor.rollback()
                        result = refusal
        finally:
            thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors, errors)
        return len(attempts), result

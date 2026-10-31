import logging
import threading
from unittest.mock import patch

from odoo import sql_db
from odoo.exceptions import UserError
from odoo.http.retrying import retrying
from odoo.tools import mute_logger

from .scheduling_committed_case import SchedulingCommittedCase

_logger = logging.getLogger(__name__)


class SchedulingConcurrencyCase(SchedulingCommittedCase):
    """Real overlapping scheduling transactions with native request commits and retries."""

    def race(self, first_action, second_action, model, method, boundary):
        """Synchronize both real transactions at the production boundary, then let request retrying resolve them."""
        gate = threading.Barrier(2, timeout=15)
        loser_checked = threading.Event()
        outcomes, errors = {}, []
        attempts = {"first": 0, "second": 0}
        real_method = getattr(type(self.env[model]), method)

        def synchronized(records, *args, **kwargs):
            name = threading.current_thread().name
            if name in attempts and boundary(records, args):
                attempts[name] += 1
                if attempts[name] == 1:
                    gate.wait()
            if method != "try_lock_for_update" or name not in attempts:
                return real_method(records, *args, **kwargs)
            try:
                locked = real_method(records, *args, **kwargs)
            except Exception:
                loser_checked.set()
                raise
            if locked:
                if not loser_checked.wait(timeout=15):
                    raise TimeoutError("The competing claimant never checked the held lock")
            else:
                loser_checked.set()
            return locked

        def worker(name, action):
            try:
                with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
                    env = self.environment(cursor)
                    try:
                        result = retrying(lambda: action(env), env, close_on_commit=False)
                        outcomes[name] = ("committed", result)
                    except UserError as error:
                        cursor.rollback()
                        outcomes[name] = ("refused", str(error))
                    cursor.flush()
                    cursor.transaction = None
            except Exception as error:
                errors.append(error)
                gate.abort()
                loser_checked.set()

        def loaded_registry(db_name):
            if db_name != self.registry.db_name:
                raise AssertionError("A scheduling race tried to open another database")
            return self.registry

        # retrying() commits and resets its transaction. Resolve that same registry without taking the suite's lock.
        with (
            patch("odoo.orm.environments.Registry", loaded_registry),
            patch.object(type(self.env[model]), method, synchronized),
            mute_logger("odoo.sql_db", "odoo.http"),
        ):
            self.workers = [
                threading.Thread(target=worker, name=name, args=(name, action), daemon=True)
                for name, action in (("first", first_action), ("second", second_action))
            ]
            for thread in self.workers:
                thread.start()
            try:
                for thread in self.workers:
                    thread.join(30)
            finally:
                gate.abort()
                loser_checked.set()
                for thread in self.workers:
                    thread.join(10)
        self.assertFalse([thread.name for thread in self.workers if thread.is_alive()], "A race worker did not stop")
        self.assertFalse(errors, errors)
        self.assertEqual(set(outcomes), {"first", "second"})
        self.assertTrue(all(count >= 1 for count in attempts.values()), attempts)
        _logger.info("Scheduling race %s.%s: outcomes=%s boundary_attempts=%s", model, method, outcomes, attempts)
        return outcomes

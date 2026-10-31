import logging
import threading
from contextlib import ExitStack
from unittest.mock import patch

import psycopg2
import psycopg2.errorcodes

from odoo import sql_db
from odoo.exceptions import ConcurrencyError, UserError
from odoo.http.retrying import retrying
from odoo.tools import SQL, mute_logger

from .scheduling_committed_case import SchedulingCommittedCase

_logger = logging.getLogger(__name__)
NAMES = ("first", "second")
# The database conflicts after which request retrying runs a transaction again, as race evidence names them.
RETRIED_CONFLICTS = frozenset({"SERIALIZATION_FAILURE", "DEADLOCK_DETECTED"})
WAIT_SECONDS = 15


class SchedulingConcurrencyCase(SchedulingCommittedCase):
    """Real overlapping scheduling transactions with native request commits and retries."""

    def race(
        self,
        first_action,
        second_action,
        model=None,
        method=None,
        boundary=None,
        *,
        boundaries=None,
        commits_first=None,
    ):
        """Synchronize both real transactions at their production boundaries, then let request retrying resolve them.

        Each thread stops at the first call of its boundary that matches its predicate until the other reaches its own:
        one boundary for both, (model, method, boundary), or one per thread, {"first": (model, method, predicate), ...}.
        With commits_first, the other thread then waits until that one has committed or been refused, so a chosen
        transaction commits while the other is open past its boundary. self.race_evidence keeps how the race ran.
        """
        if boundaries is None:
            if boundary is None:
                raise ValueError("A race needs one boundary for both threads or one per thread")
            boundaries = dict.fromkeys(NAMES, (model, method, boundary))
        gate = threading.Barrier(2, timeout=WAIT_SECONDS)
        loser_checked = threading.Event()
        finished = {name: threading.Event() for name in NAMES}
        outcomes, errors, passed, reached = {}, [], set(), {}
        hits, attempts = dict.fromkeys(NAMES, 0), dict.fromkeys(NAMES, 0)
        conflicts = {name: [] for name in NAMES}

        def synchronized(target, real_method):
            def call(records, *args, **kwargs):
                name = threading.current_thread().name
                own = name in boundaries and boundaries[name][:2] == target
                if own and boundaries[name][2](records, args):
                    hits[name] += 1
                    if hits[name] == 1:
                        reached[name] = (records._name, records.ids, args)
                        gate.wait()
                        passed.add(name)
                        if commits_first and name != commits_first and not finished[commits_first].wait(WAIT_SECONDS):
                            raise TimeoutError(f"The {commits_first} transaction did not finish")
                if target[1] != "try_lock_for_update" or not own:
                    return real_method(records, *args, **kwargs)
                try:
                    locked = real_method(records, *args, **kwargs)
                except Exception:
                    loser_checked.set()
                    raise
                if locked:
                    if not loser_checked.wait(timeout=WAIT_SECONDS):
                        raise TimeoutError("The competing claimant never checked the held lock")
                else:
                    loser_checked.set()
                return locked

            return call

        def worker(name, action):
            def attempt(env):
                attempts[name] += 1
                try:
                    result = action(env)
                    env.cr.flush()
                    return result
                except (psycopg2.Error, ConcurrencyError) as error:
                    code = getattr(error, "pgcode", None)
                    conflicts[name].append(psycopg2.errorcodes.lookup(code) if code else type(error).__name__)
                    raise

            try:
                with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
                    env = self.environment(cursor)
                    try:
                        result = retrying(lambda: attempt(env), env, close_on_commit=False)
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
            finally:
                finished[name].set()

        def loaded_registry(db_name):
            if db_name != self.registry.db_name:
                raise AssertionError("A scheduling race tried to open another database")
            return self.registry

        diagnosis = []
        with ExitStack() as stack:
            # retrying() commits and resets its transaction. Resolve that same registry without taking the suite's lock.
            stack.enter_context(patch("odoo.orm.environments.Registry", loaded_registry))
            stack.enter_context(mute_logger("odoo.sql_db", "odoo.http"))
            for target in {boundary_[:2] for boundary_ in boundaries.values()}:
                model_class = type(self.env[target[0]])
                real_method = getattr(model_class, target[1])
                stack.enter_context(patch.object(model_class, target[1], synchronized(target, real_method)))
            self.workers = [
                threading.Thread(target=worker, name=name, args=(name, action), daemon=True)
                for name, action in zip(NAMES, (first_action, second_action), strict=True)
            ]
            for thread in self.workers:
                thread.start()
            try:
                for thread in self.workers:
                    thread.join(2 * WAIT_SECONDS)
            finally:
                if errors or any(thread.is_alive() for thread in self.workers):
                    diagnosis = self.blocking_report()
                gate.abort()
                loser_checked.set()
                for thread in self.workers:
                    thread.join(10)
        self.race_evidence = {
            "outcomes": outcomes,
            "passed_barrier": sorted(passed),
            "reached": reached,
            "boundary_hits": hits,
            "attempts": attempts,
            "conflicts": conflicts,
            "commits_first": commits_first,
        }
        _logger.info("Scheduling race %s: %s", self._testMethodName, self.race_evidence)
        alive = [thread.name for thread in self.workers if thread.is_alive()]
        self.assertFalse(alive, ("A race worker did not stop", diagnosis))
        self.assertFalse(errors, (errors, diagnosis))
        self.assertEqual(set(outcomes), set(NAMES))
        self.assertEqual(passed, set(NAMES), ("Both transactions must pass the barrier at their boundary", reached))
        return outcomes

    @staticmethod
    def values(argument):
        """The values of a create call's argument, as a list."""
        return [argument] if isinstance(argument, dict) else argument

    def blocking_report(self):
        """What each other session of the database waits for, and which sessions block it."""
        with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
            cursor.execute(
                "SELECT pid, state, wait_event_type, wait_event, pg_blocking_pids(pid), left(query, 200)"
                " FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
            return cursor.fetchall()

    def park_foreign_queue(self, env):
        """Take other tests' queued bookings out of the queue until the test ends. Every replan rewrites them, so they
        would make any two scheduling transactions conflict on rows outside the race."""
        env.cr.execute(
            SQL(
                "UPDATE medilab_machine_booking SET status = 'cancelled'"
                " WHERE status = 'queued' AND sample_test_id <> ALL(%s) RETURNING id",
                self.test_ids,
            )
        )
        parked = [row[0] for row in env.cr.fetchall()]

        def restore(env):
            env.cr.execute(
                SQL(
                    "UPDATE medilab_machine_booking SET status = 'queued' WHERE id = ANY(%s) AND status = 'cancelled'",
                    parked,
                )
            )
            self.assertEqual(env.cr.rowcount, len(parked), "A parked booking was changed during the test")

        self.addCleanup(self.committed, restore)
        return parked

    def request(self, action):
        """Run the action as one request does: its own cursor and transaction, committed by request retrying.

        Returns ("committed", result), ("refused", message) for a user error, or ("failed", error) for any other error;
        nothing of a refused or failed request is committed.
        """
        attempts = 0

        def attempt(env):
            nonlocal attempts
            attempts += 1
            result = action(env)
            env.cr.flush()
            return result

        with (
            patch("odoo.orm.environments.Registry", lambda _db_name: self.registry),
            mute_logger("odoo.sql_db", "odoo.http"),
            sql_db.db_connect(self.registry.db_name).cursor() as cursor,
        ):
            env = self.environment(cursor)
            try:
                outcome = ("committed", retrying(lambda: attempt(env), env, close_on_commit=False))
            except UserError as error:
                cursor.rollback()
                outcome = ("refused", str(error))
            except Exception as error:
                cursor.rollback()
                outcome = ("failed", error)
            cursor.flush()
            cursor.transaction = None
        _logger.info("Scheduling request %s: %s after %s attempt(s)", self._testMethodName, outcome, attempts)
        return outcome
